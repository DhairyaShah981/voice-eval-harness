"""Pipecat connector — v0.1 stub.

Pipecat agents run as long-lived processes that orchestrate STT + LLM + TTS
pipelines. The voxeval Pipecat connector will speak to a running Pipecat
service via its HTTP / WebSocket transport (FastAPI + Uvicorn by default).
Full implementation in v0.2.

Tracking: https://github.com/pipecat-ai/pipecat
"""

from __future__ import annotations

from voice_eval_harness.connectors.base import BaseConnector, Session
from voice_eval_harness.core.models import ProviderSpec, TestCase


class PipecatConnector(BaseConnector):
    name = "pipecat"
    supports_audio = False

    def __init__(self, cfg: ProviderSpec) -> None:
        super().__init__(cfg)

    async def start_session(self, case: TestCase) -> Session:
        raise NotImplementedError(
            "Pipecat connector is a v0.1 stub — full HTTP/WebSocket "
            "transport support lands in v0.2. Issue tracker: "
            "https://github.com/DhairyaShah981/voice-eval-harness/issues"
        )
