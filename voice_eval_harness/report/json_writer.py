"""report.json writer — full SuiteResult serialized for downstream tools."""

from __future__ import annotations

import json
from pathlib import Path

from voice_eval_harness.core.models import SuiteResult


def write_json(result: SuiteResult, path: Path) -> None:
    payload = result.model_dump(mode="json")
    path.write_text(json.dumps(payload, indent=2))
