"""Bland.ai connector — v0.1 stub.

Bland.ai exposes an outbound-call API; the voxeval Bland connector will
wrap ``POST /v1/calls`` for audio-mode and the inbound chat endpoints
for text-mode. Full implementation in v0.2.

Tracking: https://docs.bland.ai/
"""

from __future__ import annotations

from voice_eval_harness.connectors.base import BaseConnector, Session
from voice_eval_harness.core.models import ProviderSpec, TestCase


class BlandConnector(BaseConnector):
    name = "bland"
    supports_audio = False

    def __init__(self, cfg: ProviderSpec) -> None:
        super().__init__(cfg)

    async def start_session(self, case: TestCase) -> Session:
        raise NotImplementedError(
            "Bland connector is a v0.1 stub. Full implementation in v0.2. "
            "Issue tracker: "
            "https://github.com/DhairyaShah981/voice-eval-harness/issues"
        )
