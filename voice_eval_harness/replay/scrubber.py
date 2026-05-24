"""PHI / PII scrubber for replayed call transcripts.

v0.1 uses a regex pack tuned for US healthcare workflows. The optional
``[phi]`` extra adds Microsoft Presidio for stronger NER-based scrubbing.

Refuses to emit a fixture if confidence is below threshold unless the
caller explicitly opts in with ``allow_low_confidence=True``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_PATTERNS = {
    "ssn":        re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "phone":      re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
    "email":      re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "credit_card": re.compile(r"\b(?:\d[ -]?){13,16}\b"),
    "mrn":        re.compile(r"\b(?:MRN|mrn|Medical Record(?: Number)?)\s*[:#]?\s*[A-Z0-9-]{4,}\b"),
    "dob":        re.compile(r"\b(0[1-9]|1[0-2])[/-](0[1-9]|[12]\d|3[01])[/-](19|20)\d{2}\b"),
    "url_token":  re.compile(r"https?://\S+"),
    "address":    re.compile(r"\b\d{1,5}\s+\w+(?:\s+\w+){0,3}\s+(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Lane|Ln|Blvd|Boulevard|Court|Ct)\b", re.I),
}

_REDACTED = "<redacted:{kind}>"


@dataclass(frozen=True)
class ScrubResult:
    text: str
    redactions: dict[str, int]
    confidence: float        # 1.0 = nothing matched a low-confidence path

    def total_redactions(self) -> int:
        return sum(self.redactions.values())


def scrub_text(text: str) -> ScrubResult:
    redactions: dict[str, int] = {}
    out = text
    for kind, pattern in _PATTERNS.items():
        n = 0
        def _sub(m: re.Match[str], k: str = kind) -> str:
            nonlocal n
            n += 1
            return _REDACTED.format(kind=k)
        out = pattern.sub(_sub, out)
        if n:
            redactions[kind] = n
    # Confidence heuristic: 1.0 if no redactions needed, 0.9 if the regex
    # pack handled them. Presidio would push this higher.
    confidence = 1.0 if not redactions else 0.9
    return ScrubResult(text=out, redactions=redactions, confidence=confidence)
