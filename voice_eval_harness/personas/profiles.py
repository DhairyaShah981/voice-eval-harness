"""Built-in persona profiles and the data shape the simulator consumes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PersonaProfile:
    """One persona run-spec.

    Attributes:
      type:          short name used by the simulator to load the system prompt.
      goal:          natural-language description of what the persona wants.
      exit_pass:     phrases / behaviours that mean "agent satisfied the goal".
      exit_fail:     phrases / behaviours that mean "agent gave up / escalated".
      max_turns:     hard cap on user turns the simulator will generate.
      params:        free-form per-type knobs (primary lang, accent, etc.).
      openers:       small bank of adversarial opener lines, sampled with seed.
    """

    type: str
    goal: str
    exit_pass: tuple[str, ...]
    exit_fail: tuple[str, ...]
    max_turns: int = 8
    params: dict[str, Any] = field(default_factory=dict)
    openers: tuple[str, ...] = ()


_IMPATIENT = PersonaProfile(
    type="impatient",
    goal="Book an appointment as fast as possible. Cut the agent off "
         "if they take more than one breath. Threaten to hang up after 4 turns.",
    exit_pass=("confirmed", "booked", "see you", "appointment is set",
               "your appointment"),
    exit_fail=("transfer", "human", "representative", "I cannot help"),
    openers=(
        "I don't have all day. Book me an appointment now.",
        "Skip the intro. I need an appointment tomorrow.",
        "Listen — just give me the next available slot. Don't make me repeat myself.",
    ),
)

_ACCENTED = PersonaProfile(
    type="accented",
    goal="Book an appointment while speaking with a heavy non-native accent. "
         "Speak in English but use uncommon phrasings ('I am wanting to make "
         "the appointment'). Repeat key info if the agent seems unsure.",
    exit_pass=("confirmed", "booked", "see you"),
    exit_fail=("I didn't catch that", "could not understand", "transfer"),
    openers=(
        "Hello good day, I am wanting that you book me the appointment please.",
        "Yes hi, the doctor I need to be seeing, what is the time available?",
        "Please please, I have very much pain in my ear, the appointment when?",
    ),
)

_CODE_SWITCHING = PersonaProfile(
    type="code_switching",
    goal="Switch between Spanish and English mid-sentence. The agent should "
         "stay in whichever language the user last used. Test that the agent "
         "follows the language switch and doesn't default back to English.",
    exit_pass=("hasta", "confirmado", "su cita", "see you", "confirmed"),
    exit_fail=("I only speak English", "no entiendo"),
    params={"primary": "es", "secondary": "en"},
    openers=(
        "Hola I need una cita with the doctor por favor.",
        "Buenas, can you check si Dr. Smith is available next Tuesday?",
        "Hola, necesito una cita with el cardiólogo this week.",
    ),
)

_KB_PROBING = PersonaProfile(
    type="kb_probing",
    goal="Ask increasingly specific factual questions that should be in the "
         "agent's knowledge base (insurance accepted, providers, addresses, "
         "office hours). If the agent confidently makes up a fact not in the "
         "KB, fail. If it correctly says 'I'm not sure' or looks it up, pass.",
    exit_pass=("I'll need to check", "let me look that up",
               "according to our records", "I don't have that specific"),
    exit_fail=("yes we accept", "definitely available",   # confident fabrications
               "absolutely covered"),
    openers=(
        "Do you accept Empire BlueCross BlueShield PPO for in-network rates?",
        "Is Dr. Patel still practicing at the Stockton location on Tuesdays?",
        "What's the after-hours emergency number for the cardiology service?",
    ),
)


BUILTIN_PROFILES: dict[str, PersonaProfile] = {
    p.type: p for p in (_IMPATIENT, _ACCENTED, _CODE_SWITCHING, _KB_PROBING)
}


def get_profile(name: str) -> PersonaProfile:
    if name not in BUILTIN_PROFILES:
        raise ValueError(
            f"unknown persona type {name!r}; "
            f"available: {sorted(BUILTIN_PROFILES)}"
        )
    return BUILTIN_PROFILES[name]
