"""Persona simulator drives MockConnector with a deterministic stub roller."""

from __future__ import annotations

import asyncio

from voice_eval_harness.connectors.mock import MockConnector
from voice_eval_harness.core.models import ProviderSpec, TestCase
from voice_eval_harness.personas.profiles import BUILTIN_PROFILES, get_profile
from voice_eval_harness.personas.simulator import run_persona


def test_profiles_complete() -> None:
    assert set(BUILTIN_PROFILES) == {"impatient", "accented",
                                     "code_switching", "kb_probing"}
    for prof in BUILTIN_PROFILES.values():
        assert prof.goal
        assert prof.max_turns > 0
        assert prof.openers


def test_persona_pass_when_agent_emits_exit_pass_marker() -> None:
    """Impatient persona: opener -> agent says 'confirmed' -> PASS."""
    async def run() -> None:
        cfg = ProviderSpec(name="mock")
        # MockConnector reads .responses from cfg extras.
        cfg = ProviderSpec.model_validate({
            "name": "mock",
            "responses": {"t1": [
                "Sure, your appointment is confirmed for tomorrow at 2pm.",
            ]},
        })
        conn = MockConnector(cfg)
        session = await conn.start_session(TestCase(id="t1"))
        profile = get_profile("impatient")
        result = await run_persona(
            session, profile,
            user_roller=lambda prompt: "next reply",
            opener="Book me now.",
        )
        assert result.passed, result.reason
        assert result.turns == 1

    asyncio.run(run())


def test_persona_fail_on_max_turns() -> None:
    async def run() -> None:
        cfg = ProviderSpec.model_validate({"name": "mock"})
        conn = MockConnector(cfg)
        session = await conn.start_session(TestCase(id="t2"))
        profile = get_profile("impatient")  # max_turns=8
        result = await run_persona(
            session, profile,
            user_roller=lambda prompt: "still waiting",
            opener="hurry up",
        )
        assert not result.passed
        assert result.turns == profile.max_turns
        assert "max_turns" in result.reason

    asyncio.run(run())


def test_persona_done_token_short_circuits() -> None:
    async def run() -> None:
        cfg = ProviderSpec.model_validate({"name": "mock"})
        conn = MockConnector(cfg)
        session = await conn.start_session(TestCase(id="t3"))
        profile = get_profile("kb_probing")

        # The roller's second utterance contains <DONE>; simulator must exit pass.
        calls = {"n": 0}

        def roller(prompt: str) -> str:
            calls["n"] += 1
            return "okay thanks bye <DONE>" if calls["n"] >= 1 else "another q"

        result = await run_persona(
            session, profile, user_roller=roller, opener="first user line",
        )
        assert result.passed
        assert "DONE" in result.reason

    asyncio.run(run())
