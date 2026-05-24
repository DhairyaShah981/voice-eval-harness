"""Pull historical call transcripts from a provider, group by clinic,
PHI-scrub, and persist to disk as the corpus the analyzer will consume."""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from voice_eval_harness.replay.scrubber import scrub_text


@dataclass(frozen=True)
class CallRecord:
    call_id: str
    agent_id: str
    disconnect_reason: str
    transcript: str           # PHI-scrubbed by load_corpus
    duration_ms: int
    start_ts: int
    raw_redactions: dict[str, int]


@dataclass
class ClinicCorpus:
    agent_id: str
    agent_name: str | None
    calls: list[CallRecord] = field(default_factory=list)

    @property
    def slug(self) -> str:
        # Stable, filesystem-friendly slug from the agent_id.
        h = hashlib.sha1(self.agent_id.encode()).hexdigest()[:8]
        base = (self.agent_name or self.agent_id).lower()
        safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in base)
        return f"{safe.strip('-')[:48]}-{h}"

    @property
    def failed_calls(self) -> list[CallRecord]:
        bad = ("agent_error", "dial_busy", "error_", "voicemail",
               "no_answer", "timeout")
        return [
            c for c in self.calls
            if any(b in (c.disconnect_reason or "").lower() for b in bad)
        ]

    @property
    def happy_calls(self) -> list[CallRecord]:
        return [c for c in self.calls if c not in self.failed_calls]


def group_and_scrub(
    raw_calls: list[dict[str, Any]],
    *,
    agent_name_lookup: dict[str, str] | None = None,
    use_presidio: bool = False,
) -> dict[str, ClinicCorpus]:
    """Take raw Retell call objects and produce a dict of agent_id ->
    ``ClinicCorpus`` with every transcript already PHI-scrubbed."""
    lookup = agent_name_lookup or {}
    out: dict[str, ClinicCorpus] = {}
    for c in raw_calls:
        agent_id = c.get("agent_id") or "<unknown>"
        if agent_id not in out:
            out[agent_id] = ClinicCorpus(
                agent_id=agent_id,
                agent_name=lookup.get(agent_id),
            )
        transcript = c.get("transcript") or ""
        sr = scrub_text(transcript, use_presidio=use_presidio)
        out[agent_id].calls.append(CallRecord(
            call_id=c.get("call_id") or "?",
            agent_id=agent_id,
            disconnect_reason=c.get("disconnection_reason") or "unknown",
            transcript=sr.text,
            duration_ms=int(c.get("duration_ms") or 0),
            start_ts=int(c.get("start_timestamp") or 0),
            raw_redactions=sr.redactions,
        ))
    return out


def stratified_sample(
    corpus: ClinicCorpus,
    *,
    max_calls: int = 40,
    happy_ratio: float = 0.6,
    seed: int = 7,
) -> list[CallRecord]:
    """Pick a representative subset weighted toward including all failure
    modes plus a sample of happy paths."""
    rng = random.Random(seed)
    failed = corpus.failed_calls
    happy = corpus.happy_calls

    n_happy = min(int(max_calls * happy_ratio), len(happy))
    n_failed = min(max_calls - n_happy, len(failed))
    sample_happy = rng.sample(happy, n_happy) if happy else []
    sample_failed = rng.sample(failed, n_failed) if failed else []
    out = sample_happy + sample_failed
    rng.shuffle(out)
    return out


def write_corpus_to_disk(
    corpus: ClinicCorpus, out_dir: Path,
    *, sample: list[CallRecord] | None = None,
) -> dict[str, int]:
    """Persist (scrubbed) transcripts as plain-text files under
    ``out_dir/transcripts/``. Returns a small stats summary."""
    out_dir.mkdir(parents=True, exist_ok=True)
    tdir = out_dir / "transcripts"
    tdir.mkdir(exist_ok=True)
    calls = sample if sample is not None else corpus.calls
    for c in calls:
        path = tdir / f"{c.call_id}.txt"
        path.write_text(
            f"# call_id={c.call_id}  disconnect={c.disconnect_reason}\n"
            f"# duration_ms={c.duration_ms}\n\n"
            f"{c.transcript}\n",
        )
    return {
        "transcripts_written": len(calls),
        "happy_in_sample": sum(1 for c in calls if c not in corpus.failed_calls),
        "failed_in_sample": sum(1 for c in calls if c in corpus.failed_calls),
    }
