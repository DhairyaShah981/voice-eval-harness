"""Connector contract.

A connector knows how to talk to one voice-agent platform (Retell, Vapi,
LiveKit, ...). A connector's ``start_session`` returns a ``Session`` object
the engine drives turn-by-turn.

Connectors are async because real ones make network calls. The MockConnector
is fully in-memory but still implements the async interface so the engine
code path is identical in tests.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import ClassVar

from voice_eval_harness.core.models import (
    CallSummary,
    ProviderSpec,
    TestCase,
    TranscriptEvent,
)


class Session(ABC):
    @abstractmethod
    async def send_user_turn(
        self,
        text: str,
        *,
        lang: str | None = None,
        interrupt_at_ms: int | None = None,
    ) -> TranscriptEvent:
        """Send one user utterance, return the agent's reply event."""

    @abstractmethod
    async def stream_events(self) -> AsyncIterator[TranscriptEvent]:
        """Return any out-of-band events accumulated since the last turn
        (tool calls, system messages). Iterator is exhausted after one pass."""

    @abstractmethod
    async def end(self) -> CallSummary:
        """Wrap up the session and return aggregates."""

    @property
    @abstractmethod
    def transcript(self) -> list[TranscriptEvent]:
        """Read-only view of every event recorded this session."""


class BaseConnector(ABC):
    name: ClassVar[str] = ""
    supports_audio: ClassVar[bool] = False

    def __init__(self, cfg: ProviderSpec) -> None:
        self.cfg = cfg

    @abstractmethod
    async def start_session(self, case: TestCase) -> Session:
        """Open a new session for one test case."""
