"""LiveKit Agents connector — v0.1 stub.

LiveKit ships a first-party test framework (``AgentSession.run().expect.judge``)
that's tightly bound to the in-process Python agent class. To run LiveKit
agents through voxeval (so you get the same persona simulator, KB coverage,
and replay tooling as Retell/Vapi), the connector calls into the LiveKit
test helpers directly rather than over HTTP.

This stub registers the ``livekit`` provider name and gives a clear,
actionable error if invoked. Full implementation lands in v0.2 once we
pin a LiveKit SDK version compatible with the test harness API.

Tracking: https://docs.livekit.io/agents/start/testing/
"""

from __future__ import annotations

from voice_eval_harness.connectors.base import BaseConnector, Session
from voice_eval_harness.core.models import ProviderSpec, TestCase


class LiveKitConnector(BaseConnector):
    name = "livekit"
    supports_audio = False  # v0.1 stub — full audio support in v0.2

    def __init__(self, cfg: ProviderSpec) -> None:
        super().__init__(cfg)

    async def start_session(self, case: TestCase) -> Session:
        raise NotImplementedError(
            "LiveKit connector is a v0.1 stub. The LiveKit Agents framework "
            "ships its own test helpers (https://docs.livekit.io/agents/start/testing/) "
            "that we will wrap in v0.2. For now, write LiveKit tests with "
            "the first-party `AgentSession.run().expect.judge()` API and "
            "use voxeval for your Retell/Vapi connectors. Star the repo to "
            "be notified when v0.2 ships: "
            "https://github.com/DhairyaShah981/voice-eval-harness"
        )
