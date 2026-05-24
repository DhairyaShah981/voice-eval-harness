"""Each broken fixture must be flagged by exactly its target rule (no rule misses
its own bug, no other rule false-positives). The clean fixture must pass."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fixtures.build_broken_variants import CLEAN, OUT, VARIANTS
from voice_eval_harness.linters.retell import RETELL_RULES
from voice_eval_harness.linters.runner import lint_file

FIXTURE_DIR = Path(OUT)


def test_clean_fixture_passes() -> None:
    report = lint_file(CLEAN, RETELL_RULES)
    assert report.ok, f"clean fixture produced fatals: {[i.render() for i in report.fatals]}"


@pytest.mark.parametrize("variant", sorted(VARIANTS.keys()))
def test_broken_variant_fires_target_rule(variant: str) -> None:
    expected_rule = VARIANTS[variant][1]
    report = lint_file(FIXTURE_DIR / variant, RETELL_RULES)
    rule_ids_fired = {i.rule_id for i in report.issues}
    assert expected_rule in rule_ids_fired, (
        f"variant {variant} should fire {expected_rule}; "
        f"fired={sorted(rule_ids_fired)}"
    )
