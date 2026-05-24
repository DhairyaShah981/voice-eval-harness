"""Match agent responses against expected KB answers.

Two backends:
  - ``llm_judge`` (default): reuse the LLM judge with a fixed criterion.
    Accurate for domain-specific facts; inherits the judge's disk cache.
  - ``sentence_transformers``: offline cosine similarity using
    all-MiniLM-L6-v2 from the ``[kb]`` extra. Free per call after the
    one-time model download. Less precise on paraphrase-heavy answers.

Backend is selected via the ``matcher`` field on the KBCoverageSpec
(or programmatically by passing ``backend=``).
"""

from __future__ import annotations

from typing import Literal

from voice_eval_harness.assertions.llm_judge import LLMJudgeAssertion
from voice_eval_harness.core.models import (
    AssertionSpec,
    CallSummary,
    Role,
    TranscriptEvent,
)

Backend = Literal["llm_judge", "sentence_transformers"]


def agent_matches_answer(
    agent_reply: str,
    expected_answer: str,
    question: str,
    *,
    backend: Backend = "llm_judge",
) -> bool:
    """Return True iff the agent reply satisfies the expected answer."""
    if backend == "sentence_transformers":
        from voice_eval_harness.kb.st_matcher import cosine_match
        return cosine_match(agent_reply, expected_answer)
    transcript = [
        TranscriptEvent(role=Role.USER, text=question, ts_ms=0),
        TranscriptEvent(role=Role.AGENT, text=agent_reply, ts_ms=100),
    ]
    spec = AssertionSpec(
        kind="llm_judge",
        criterion=(
            "The agent's response correctly conveys the same information "
            f"as the expected answer: '{expected_answer}'. Minor wording "
            "differences are fine; factual content must match. If the "
            "agent says 'I don't know' or hedges, that is FAIL."
        ),
    )
    res = LLMJudgeAssertion(spec).evaluate(transcript, CallSummary())
    return res.passed
