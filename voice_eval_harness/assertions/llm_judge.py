"""LLM-judge assertion.

A judge model (default ``gpt-4o-mini-2024-07-18``, temp 0) is asked
whether the agent's behavior satisfied a free-form criterion. Results
are cached on disk by ``sha1(transcript + criterion + model)`` to bound
cost on re-runs.

The judge is pluggable: any callable with the signature
``(prompt: str, model: str) -> dict`` can be passed in for tests. The
real client uses the OpenAI SDK.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from voice_eval_harness.assertions.base import (
    Assertion,
    _agent_text,
)

if TYPE_CHECKING:
    from voice_eval_harness.core.budget import BudgetTracker
from voice_eval_harness.core.models import (
    AssertionResult,
    AssertionSpec,
    CallSummary,
    TranscriptEvent,
)

JudgeFn = Callable[[str, str], dict[str, Any]]
"""Signature: (rendered_prompt, model_name) -> {verdict: pass|fail, reason: str}."""

DEFAULT_JUDGE_MODEL = os.environ.get(
    "VOXEVAL_JUDGE_MODEL", "gpt-4o-mini-2024-07-18",
)

_JUDGE_TEMPLATE = """\
You are an evaluator for a voice AI agent. Your job is to decide whether the
agent satisfied a stated criterion based on the transcript below.

Criterion:
{criterion}

Transcript (user / agent turns and tool calls):
{transcript}

Return ONLY a JSON object on a single line with this exact shape:
{{"verdict": "pass" | "fail", "reason": "<one sentence>"}}
"""


def _render_transcript(transcript: list[TranscriptEvent]) -> str:
    lines: list[str] = []
    for e in transcript:
        if e.role.value == "tool" and e.tool_name:
            args = json.dumps(e.tool_args or {}, ensure_ascii=False)
            lines.append(f"[tool:{e.tool_name}] {args}")
        else:
            lines.append(f"[{e.role.value}] {e.text or ''}")
    return "\n".join(lines)


def _openai_judge(prompt: str, model: str) -> dict[str, Any]:  # pragma: no cover
    """Real OpenAI call. Tests use a fake judge_fn instead."""
    from openai import OpenAI  # imported lazily so the package installs without openai
    client = OpenAI()
    resp = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[
            {"role": "system",
             "content": "You output only valid JSON. No prose."},
            {"role": "user", "content": prompt},
        ],
    )
    raw = resp.choices[0].message.content or "{}"
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Last-resort: try to find the first {...} block.
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            return json.loads(raw[start:end + 1])
        return {"verdict": "fail", "reason": f"judge returned non-JSON: {raw[:200]}"}


def _cache_key(prompt: str, model: str) -> str:
    h = hashlib.sha1(f"{model}\n{prompt}".encode()).hexdigest()
    return h[:16]


class LLMJudgeAssertion(Assertion):
    """Semantic intent assertion. Spec params:

      criterion: str   — the natural-language test criterion.
      model:     str   — override the judge model (else env default).
    """

    kind = "llm_judge"

    # Class-level injection points so tests can swap the judge and cache.
    judge_fn: JudgeFn | None = None
    cache_dir: Path | None = None  # default: ./.voxeval_cache/
    # Set by the engine before run_suite kicks off (None = unlimited).
    budget: BudgetTracker | None = None

    def __init__(self, spec: AssertionSpec) -> None:
        super().__init__(spec)
        self.criterion: str = self.params.get("criterion", "")
        self.model: str = self.params.get("model") or DEFAULT_JUDGE_MODEL

    def evaluate(
        self, transcript: list[TranscriptEvent], summary: CallSummary,
    ) -> AssertionResult:
        if not self.criterion:
            return AssertionResult(
                kind=self.kind, passed=False,
                detail="llm_judge: missing 'criterion' in spec",
            )
        # The legacy assertion code uses _agent_text just for the contains
        # family; the judge sees the full transcript so it can reason about
        # tool calls + user turns.
        _ = _agent_text  # kept to avoid an unused-import warning under ruff
        prompt = _JUDGE_TEMPLATE.format(
            criterion=self.criterion,
            transcript=_render_transcript(transcript),
        )
        cache_dir = self.cache_dir or Path(".voxeval_cache")
        cache_dir.mkdir(parents=True, exist_ok=True)
        key = _cache_key(prompt, self.model)
        cache_file = cache_dir / f"judge_{key}.json"

        if cache_file.exists():
            data = json.loads(cache_file.read_text())
        else:
            # Charge the budget BEFORE the call so a runaway suite never
            # makes the API hit. Cache hits are free.
            if self.budget is not None:
                from voice_eval_harness.core.budget import DEFAULT_JUDGE_COST_USD
                if not self.budget.try_spend_sync(DEFAULT_JUDGE_COST_USD):
                    return AssertionResult(
                        kind=self.kind, passed=False,
                        detail=("skipped_budget: --max-cost ceiling "
                                f"${self.budget.max_cost_usd:.2f} would be "
                                f"exceeded (spent ${self.budget.spent_usd:.4f})"),
                    )
            fn = self.judge_fn or _openai_judge
            try:
                data = fn(prompt, self.model)
            except Exception as exc:  # noqa: BLE001
                return AssertionResult(
                    kind=self.kind, passed=False,
                    detail=f"judge_call_failed: {type(exc).__name__}: {exc}",
                )
            cache_file.write_text(json.dumps(data))

        verdict = (data.get("verdict") or "").lower()
        reason = data.get("reason") or ""
        return AssertionResult(
            kind=self.kind,
            passed=(verdict == "pass"),
            detail=reason if verdict != "pass" else "",
        )
