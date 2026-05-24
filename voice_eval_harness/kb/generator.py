"""Q/A pair generation from KB chunks.

For each chunk, ask the generator model for ``per_chunk`` Q/A pairs. Each
pair gets a verification pass (same model) asking 'is this Q answerable
from this chunk alone, and is the A factually supported by the chunk?'.
Verified pairs are persisted to a JSONL cache keyed by
``sha1(chunk_text + model)`` so reruns are free.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from voice_eval_harness.kb.loader import KbChunk

DEFAULT_GEN_MODEL = os.environ.get("VOXEVAL_KB_GEN_MODEL", "gpt-4o-2024-08-06")

GeneratorFn = Callable[[str, str], list[dict[str, Any]]]
"""Signature: (chunk_text, model) -> [{question, answer}, ...]."""

VerifierFn = Callable[[str, str, str, str], bool]
"""Signature: (chunk_text, question, answer, model) -> verified?"""


@dataclass(frozen=True)
class QaPair:
    chunk_id: str
    source: str
    section: str
    question: str
    answer: str


_GEN_PROMPT = """\
Source chunk (markdown):
---
{chunk}
---

Generate exactly {n} factual question-answer pairs that:
  - can be answered SOLELY from the source chunk above (no outside knowledge),
  - cover concrete facts (names, numbers, addresses, policies, hours, eligibility),
  - have answers that are short (1-2 sentences max).

Return ONLY a JSON array on a single line with this exact shape:
[{{"question": "...", "answer": "..."}}, ...]
"""

_VERIFY_PROMPT = """\
Source chunk:
---
{chunk}
---

Question: {q}
Answer:   {a}

Is this answer fully supported by the source chunk above (no hallucination,
no outside knowledge needed)? Reply with ONLY the word "yes" or "no".
"""


def _openai_generator(chunk_text: str, model: str) -> list[dict[str, Any]]:  # pragma: no cover
    from openai import OpenAI
    client = OpenAI()
    resp = client.chat.completions.create(
        model=model, temperature=0,
        messages=[{"role": "user", "content": _GEN_PROMPT.format(chunk=chunk_text, n=3)}],
    )
    raw = (resp.choices[0].message.content or "[]").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("[")
        end = raw.rfind("]")
        if start >= 0 and end > start:
            return json.loads(raw[start:end + 1])
        return []


def _openai_verifier(chunk_text: str, q: str, a: str, model: str) -> bool:  # pragma: no cover
    from openai import OpenAI
    client = OpenAI()
    resp = client.chat.completions.create(
        model=model, temperature=0,
        messages=[{"role": "user",
                   "content": _VERIFY_PROMPT.format(chunk=chunk_text, q=q, a=a)}],
    )
    raw = (resp.choices[0].message.content or "").strip().lower()
    return raw.startswith("y")


def _cache_key(chunk_text: str, model: str) -> str:
    return hashlib.sha1(f"{model}\n{chunk_text}".encode()).hexdigest()[:16]


def build_qa_bank(
    chunks: list[KbChunk],
    *,
    model: str = DEFAULT_GEN_MODEL,
    generator: GeneratorFn | None = None,
    verifier: VerifierFn | None = None,
    cache_dir: Path | None = None,
    skip_verification: bool = False,
) -> list[QaPair]:
    """Produce a verified Q/A bank for the given chunks. Cached on disk."""
    cache_dir = cache_dir or Path(".voxeval_cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    gen = generator or _openai_generator
    ver = verifier or _openai_verifier

    out: list[QaPair] = []
    for chunk in chunks:
        key = _cache_key(chunk.text, model)
        cache_file = cache_dir / f"kb_qa_{key}.jsonl"
        verified: list[dict[str, Any]] = []
        if cache_file.exists():
            verified = [json.loads(line) for line in cache_file.read_text().splitlines()
                        if line.strip()]
        else:
            raw = gen(chunk.text, model)
            for pair in raw:
                q = (pair.get("question") or "").strip()
                a = (pair.get("answer") or "").strip()
                if not q or not a:
                    continue
                if skip_verification or ver(chunk.text, q, a, model):
                    verified.append({"question": q, "answer": a})
            cache_file.write_text(
                "\n".join(json.dumps(p, ensure_ascii=False) for p in verified) + "\n"
            )
        for p in verified:
            out.append(QaPair(
                chunk_id=chunk.chunk_id,
                source=chunk.source,
                section=chunk.section,
                question=p["question"],
                answer=p["answer"],
            ))
    return out
