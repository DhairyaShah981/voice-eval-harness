"""Q/A generator with a stub LLM: verifier filters bad pairs; cache hit on rerun."""

from __future__ import annotations

from pathlib import Path

from voice_eval_harness.kb.generator import build_qa_bank
from voice_eval_harness.kb.loader import KbChunk


def _chunks() -> list[KbChunk]:
    return [
        KbChunk(source="kb/01.md", section="Stockton", chunk_id="c1",
                text="Dr. Patel sees patients Tuesdays and Thursdays."),
        KbChunk(source="kb/02.md", section="Insurance", chunk_id="c2",
                text="We accept Blue Shield PPO and Aetna HMO."),
    ]


def test_generator_uses_stub_and_verifier(tmp_path: Path) -> None:
    gen_calls: list[str] = []

    def fake_gen(chunk: str, model: str) -> list[dict]:
        gen_calls.append(chunk)
        return [
            {"question": "Q1 about " + chunk[:10], "answer": "A1"},
            {"question": "Q2 about " + chunk[:10], "answer": "A2"},
            {"question": "", "answer": "missing q"},   # filtered (empty Q)
        ]

    verifier_calls: list[tuple[str, str]] = []

    def fake_verify(chunk: str, q: str, a: str, model: str) -> bool:
        verifier_calls.append((q, a))
        return "Q1" in q  # only Q1 pairs survive

    bank = build_qa_bank(
        _chunks(), generator=fake_gen, verifier=fake_verify, cache_dir=tmp_path,
    )
    questions = [p.question for p in bank]
    assert all("Q1" in q for q in questions)
    assert len(questions) == 2
    # 2 chunks × 2 non-empty raw pairs = 4 verifier calls
    assert len(verifier_calls) == 4


def test_generator_cache_hit_on_rerun(tmp_path: Path) -> None:
    gen_calls: list[str] = []

    def fake_gen(chunk: str, model: str) -> list[dict]:
        gen_calls.append(chunk)
        return [{"question": "Q", "answer": "A"}]

    bank1 = build_qa_bank(
        _chunks(), generator=fake_gen,
        verifier=lambda *a, **k: True, cache_dir=tmp_path,
    )
    bank2 = build_qa_bank(
        _chunks(), generator=fake_gen,
        verifier=lambda *a, **k: True, cache_dir=tmp_path,
    )
    assert len(bank1) == len(bank2)
    # Generator should have been called once per chunk, not twice.
    assert len(gen_calls) == len(_chunks())


def test_skip_verification_passes_all(tmp_path: Path) -> None:
    bank = build_qa_bank(
        _chunks(),
        generator=lambda c, m: [{"question": "q1", "answer": "a1"}],
        verifier=lambda *a, **k: False,   # would reject all if called
        cache_dir=tmp_path,
        skip_verification=True,
    )
    assert len(bank) == len(_chunks())
