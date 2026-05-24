"""Persona simulator — an LLM rolls the user side of the call.

Given a ``PersonaProfile`` and an open ``Session``, the simulator picks the
next user utterance based on the running transcript, the persona's goal,
and the exit conditions. The loop ends when:

  - an exit_pass marker appears in an agent turn (PASS),
  - an exit_fail marker appears in an agent turn (FAIL),
  - the persona's ``max_turns`` cap is hit (FAIL).

The "user-roller" is pluggable: any callable with the signature
``(prompt: str) -> str`` works. The real one uses the OpenAI SDK; tests
pass a deterministic stub.
"""

from __future__ import annotations

import os
import random
from collections.abc import Callable
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from voice_eval_harness.connectors.base import Session
from voice_eval_harness.core.models import Role, TranscriptEvent
from voice_eval_harness.personas.profiles import PersonaProfile

UserRollerFn = Callable[[str], str]
"""Signature: rendered system+history prompt -> next user utterance."""

DEFAULT_PERSONA_MODEL = os.environ.get(
    "VOXEVAL_PERSONA_MODEL", "gpt-4o-mini-2024-07-18",
)

# Per-persona prompts live as Jinja templates so users can override them
# by dropping a file at ``./personas/prompts/<type>.jinja`` in their project
# root (precedence: cwd > package). The fallback template applies when no
# persona-specific file exists.
_PACKAGE_PROMPTS = Path(__file__).parent / "prompts"
_FALLBACK_PROMPT = """\
You are roleplaying a CALLER on a phone call with a voice AI agent.

PERSONA ({{ type }}):
{{ goal }}

Adversarial style:
  - Stay in character at all times.
  - Generate ONE next user utterance (one or two sentences max).
  - Do not narrate. Do not break the fourth wall. No quotes.
  - If you have accomplished your goal, end with the literal token <DONE>.

Conversation so far (oldest to newest):
{{ transcript }}

Your next utterance:
"""


def _render_prompt(profile: PersonaProfile, transcript_text: str) -> str:
    """Render the persona prompt — user override takes precedence over packaged."""
    candidates = [
        Path.cwd() / "personas" / "prompts" / f"{profile.type}.jinja",
        _PACKAGE_PROMPTS / f"{profile.type}.jinja",
    ]
    template_dir: Path | None = None
    for c in candidates:
        if c.exists():
            template_dir = c.parent
            template_name = c.name
            break
    if template_dir is None:
        # Use the inline fallback.
        env = Environment(autoescape=select_autoescape([]))
        tmpl = env.from_string(_FALLBACK_PROMPT)
    else:
        env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=select_autoescape([]),
        )
        tmpl = env.get_template(template_name)
    return tmpl.render(
        type=profile.type,
        goal=profile.goal,
        transcript=transcript_text,
    )


def _render_transcript(events: list[TranscriptEvent]) -> str:
    if not events:
        return "(none yet)"
    lines: list[str] = []
    for e in events:
        if e.role == Role.AGENT:
            lines.append(f"AGENT: {e.text or ''}")
        elif e.role == Role.USER:
            lines.append(f"YOU:   {e.text or ''}")
        elif e.role == Role.TOOL and e.tool_name:
            lines.append(f"(agent called tool {e.tool_name})")
    return "\n".join(lines)


def _openai_user_roller(prompt: str) -> str:  # pragma: no cover
    from openai import OpenAI
    client = OpenAI()
    resp = client.chat.completions.create(
        model=DEFAULT_PERSONA_MODEL,
        temperature=0.7,
        messages=[{"role": "user", "content": prompt}],
    )
    return (resp.choices[0].message.content or "").strip()


class PersonaRunResult:
    def __init__(
        self,
        *,
        outcome: str,
        turns: int,
        reason: str,
        transcript: list[TranscriptEvent],
    ) -> None:
        self.outcome = outcome  # "pass" | "fail"
        self.turns = turns
        self.reason = reason
        self.transcript = transcript

    @property
    def passed(self) -> bool:
        return self.outcome == "pass"


def _matches(text: str, markers: tuple[str, ...]) -> str | None:
    lower = (text or "").lower()
    for m in markers:
        if m.lower() in lower:
            return m
    return None


async def run_persona(
    session: Session,
    profile: PersonaProfile,
    *,
    user_roller: UserRollerFn | None = None,
    seed: int | None = 7,
    opener: str | None = None,
) -> PersonaRunResult:
    """Drive a session with an LLM-rolled persona until an exit condition."""
    rng = random.Random(seed)
    roller = user_roller or _openai_user_roller

    if opener is None and profile.openers:
        opener = rng.choice(list(profile.openers))

    turns = 0
    last_user: str | None = opener

    while turns < profile.max_turns:
        text = last_user
        if text is None:
            prompt = _render_prompt(profile, _render_transcript(session.transcript))
            text = roller(prompt).strip()

        if "<DONE>" in text:
            text = text.replace("<DONE>", "").strip()
            if text:
                await session.send_user_turn(text)
            return PersonaRunResult(
                outcome="pass", turns=turns,
                reason="persona signalled DONE",
                transcript=list(session.transcript),
            )

        agent_reply = await session.send_user_turn(text)
        turns += 1
        last_user = None

        agent_text = agent_reply.text or ""
        pass_hit = _matches(agent_text, profile.exit_pass)
        fail_hit = _matches(agent_text, profile.exit_fail)
        if pass_hit:
            return PersonaRunResult(
                outcome="pass", turns=turns,
                reason=f"exit_pass marker '{pass_hit}' matched in agent reply",
                transcript=list(session.transcript),
            )
        if fail_hit:
            return PersonaRunResult(
                outcome="fail", turns=turns,
                reason=f"exit_fail marker '{fail_hit}' matched in agent reply",
                transcript=list(session.transcript),
            )

    return PersonaRunResult(
        outcome="fail", turns=turns,
        reason=f"max_turns ({profile.max_turns}) reached without success",
        transcript=list(session.transcript),
    )
