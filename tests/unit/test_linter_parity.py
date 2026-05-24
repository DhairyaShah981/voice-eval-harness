"""Parity test: voxeval's linter and the vendored legacy validator must
agree on every fixture.

Rules:
  - clean fixture: both linters produce zero fatals.
  - broken variant flagged by a rule the legacy validator knows about:
    both linters produce at least one issue (fatal or warning) on the file.
  - broken variant flagged by a voice-eval-harness extension rule
    (RTL-016 ngrok, RTL-017 KB empty-but-referenced): the legacy
    validator does NOT know about it, so only our linter must catch it,
    and our linter must specifically fire the target rule id.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from tests.fixtures.build_broken_variants import CLEAN, OUT, VARIANTS
from voice_eval_harness.linters.retell import RETELL_RULES
from voice_eval_harness.linters.runner import lint_file

_VENDOR = Path(__file__).resolve().parents[2] / "voice_eval_harness" / "_vendor"
sys.path.insert(0, str(_VENDOR))

from validate_retell_agent import validate as legacy_validate  # noqa: E402

NEW_ONLY_RULES = {"RTL-016", "RTL-017"}


def _legacy_buckets(path: Path) -> tuple[list[str], list[str]]:
    d = json.loads(path.read_text())
    lines = legacy_validate(d, None)
    fatals = [line for line in lines if line.lstrip().startswith("❌")]
    warns = [line for line in lines if line.lstrip().startswith("⚠")]
    return fatals, warns


def test_parity_clean_fixture() -> None:
    legacy_fatals, _ = _legacy_buckets(CLEAN)
    report = lint_file(CLEAN, RETELL_RULES)
    assert not legacy_fatals, f"legacy validator unexpectedly flagged clean: {legacy_fatals}"
    assert report.ok, f"new linter unexpectedly flagged clean: {[i.render() for i in report.fatals]}"


@pytest.mark.parametrize("variant", sorted(VARIANTS.keys()))
def test_parity_broken_variants(variant: str) -> None:
    path = OUT / variant
    target_rule = VARIANTS[variant][1]
    report = lint_file(path, RETELL_RULES)
    rule_ids_fired = {i.rule_id for i in report.issues}

    if target_rule in NEW_ONLY_RULES:
        # The legacy validator does not implement these checks; we only
        # require that our linter fires the target rule id on this fixture.
        assert target_rule in rule_ids_fired, (
            f"new rule {target_rule} did not fire on {variant}; "
            f"fired={sorted(rule_ids_fired)}"
        )
        return

    legacy_fatals, legacy_warns = _legacy_buckets(path)
    legacy_total = len(legacy_fatals) + len(legacy_warns)
    assert legacy_total > 0, (
        f"legacy validator silent on {variant} (expected to flag)"
    )
    assert report.issues, (
        f"new linter silent on {variant}; legacy flagged: "
        f"{legacy_fatals + legacy_warns}"
    )
