"""Turn a Retell call transcript into a deterministic TestCase fixture."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from voice_eval_harness.replay.scrubber import scrub_text


@dataclass(frozen=True)
class ReplayFixture:
    case_id: str               # stable, hash-derived
    user_turns: list[str]      # already PHI-scrubbed
    disconnect_reason: str
    source_call_id: str
    failure_signature: str     # short error string we don't want to see again
    raw_redactions: dict[str, int]


_TURN_LINE = re.compile(r"^\s*(?P<role>User|Agent|Tool)\s*:\s*(?P<text>.*?)\s*$",
                        re.IGNORECASE | re.MULTILINE)


def parse_transcript(transcript: str) -> list[tuple[str, str]]:
    """Extract (role, text) pairs from Retell's plaintext transcript.

    Retell renders transcripts as lines of ``User: ...`` / ``Agent: ...``.
    We tolerate other whitespace and casing.
    """
    out: list[tuple[str, str]] = []
    for m in _TURN_LINE.finditer(transcript or ""):
        role = m.group("role").lower()
        text = m.group("text").strip()
        if text:
            out.append((role, text))
    return out


def _signature(disconnect_reason: str, transcript: str) -> str:
    short = transcript.strip()[-200:].lower()
    keyword_hit = re.search(r"(error|exception|sorry|cannot|fail|hang)", short)
    if keyword_hit:
        return keyword_hit.group(0)
    return disconnect_reason or "unknown_failure"


def extract_fixture(
    call: dict[str, Any],
    *,
    max_user_turns: int = 3,
) -> ReplayFixture | None:
    """Slice the first N user turns out of a Retell call object and return a
    PHI-scrubbed ``ReplayFixture``. Returns None if the call has no usable
    user turns."""
    transcript = call.get("transcript") or ""
    turns = parse_transcript(transcript)
    user_turns_raw = [text for role, text in turns if role == "user"][:max_user_turns]
    if not user_turns_raw:
        return None

    redactions_total: dict[str, int] = {}
    scrubbed: list[str] = []
    for t in user_turns_raw:
        sr = scrub_text(t)
        scrubbed.append(sr.text)
        for k, v in sr.redactions.items():
            redactions_total[k] = redactions_total.get(k, 0) + v

    disconnect_reason = call.get("disconnection_reason") or "unknown"
    signature = _signature(disconnect_reason, transcript)
    hash_input = "\n".join(scrubbed) + "\n" + disconnect_reason
    case_id = "replay_" + hashlib.sha1(hash_input.encode()).hexdigest()[:10]
    return ReplayFixture(
        case_id=case_id,
        user_turns=scrubbed,
        disconnect_reason=disconnect_reason,
        source_call_id=call.get("call_id") or "",
        failure_signature=signature,
        raw_redactions=redactions_total,
    )


def fixture_to_yaml_dict(fix: ReplayFixture) -> dict[str, Any]:
    """Render a fixture as the dict shape voxeval YAML expects under `cases`."""
    return {
        "id": fix.case_id,
        "description": (
            f"Replay of {fix.source_call_id} "
            f"(disconnect={fix.disconnect_reason})"
        ),
        "script": [{"user_says": t} for t in fix.user_turns],
        "suite_asserts": [
            {"assert_no_crash": True},
            {"assert_not_contains": [fix.failure_signature]},
        ],
    }
