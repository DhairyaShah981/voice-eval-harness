"""Connector registry. Connectors register themselves by name so the engine
can look them up from a YAML provider spec."""

from __future__ import annotations

from voice_eval_harness.connectors.base import BaseConnector
from voice_eval_harness.connectors.mock import MockConnector
from voice_eval_harness.connectors.retell import RetellConnector
from voice_eval_harness.connectors.vapi import VapiConnector
from voice_eval_harness.core.models import ProviderSpec

CONNECTORS: dict[str, type[BaseConnector]] = {
    MockConnector.name: MockConnector,
    RetellConnector.name: RetellConnector,
    VapiConnector.name: VapiConnector,
}


def get_connector(cfg: ProviderSpec) -> BaseConnector:
    cls = CONNECTORS.get(cfg.name)
    if cls is None:
        raise ValueError(
            f"no connector registered for provider {cfg.name!r}; "
            f"known: {sorted(CONNECTORS)}"
        )
    return cls(cfg)
