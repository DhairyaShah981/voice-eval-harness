"""Match agent responses against expected KB answers.

v0.1 default: reuse the LLM judge. For each (question, expected_answer)
pair, we ask the judge whether the agent's response satisfies the expected
answer's intent. This is more accurate than embedding similarity for
domain-specific facts and inherits the judge's deterministic cache.

Sentence-transformer cosine similarity ships as an optional offline-batch
mode in v0.2 (heavy 500MB model dep is opt-in via the ``[kb]`` extra).
"""

from __future__ import annotations

from voice_eval_harness.assertions.llm_judge import LLMJudgeAssertion
from voice_eval_harness.core.models import (
    AssertionSpec,
    CallSummary,
    Role,
    TranscriptEvent,
)


def agent_matches_answer(
    agent_reply: str,
    expected_answer: str,
    question: str,
) -> bool:
    """Return True iff the agent reply satisfies the expected answer."""
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
