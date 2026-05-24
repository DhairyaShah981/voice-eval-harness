"""`voxeval diff` file-vs-file mode + cost_by_persona breakdown + jinja prompts."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from typer.testing import CliRunner

from voice_eval_harness.cli.app import app
from voice_eval_harness.core.engine import run_suite
from voice_eval_harness.core.models import (
    AssertionResult,
    EvalSuite,
    PersonaSpec,
    ProviderSpec,
    RunResult,
    SuiteResult,
    TestCase,
    Turn,
)
from voice_eval_harness.personas.profiles import get_profile
from voice_eval_harness.personas.simulator import _render_prompt

runner = CliRunner()


def _write_report(path: Path, cases: list[tuple[str, bool]]) -> None:
    res = SuiteResult(
        total_cost_usd=0.0,
        cases=[
            RunResult(case_id=cid, passed=passed, duration_ms=100,
                      assertion_results=[
                          AssertionResult(kind="contains", passed=passed),
                      ])
            for cid, passed in cases
        ],
    )
    path.write_text(json.dumps(res.model_dump(mode="json")))


def test_diff_file_vs_file_table_and_exit(tmp_path: Path) -> None:
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    # A passes all 3; B regresses on case3.
    _write_report(a, [("c1", True), ("c2", True), ("c3", True)])
    _write_report(b, [("c1", True), ("c2", True), ("c3", False)])

    out_json = tmp_path / "diff.json"
    result = runner.invoke(app, [
        "diff", str(a), str(b),
        "--name-a", "main", "--name-b", "feature",
        "--json-out", str(out_json),
    ])
    assert result.exit_code == 1, result.stdout  # regression -> exit 1
    payload = json.loads(out_json.read_text())
    assert payload["left"] == "main"
    assert payload["right"] == "feature"
    rows = {r["case_id"]: r for r in payload["cases"]}
    assert rows["c3"]["main"]["passed"] is True
    assert rows["c3"]["feature"]["passed"] is False


def test_diff_no_regressions_returns_zero(tmp_path: Path) -> None:
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    _write_report(a, [("c1", True)])
    _write_report(b, [("c1", True)])
    result = runner.invoke(app, ["diff", str(a), str(b)])
    assert result.exit_code == 0


def test_cost_by_persona_breakdown_present() -> None:
    suite = EvalSuite(
        provider=ProviderSpec(name="mock"),
        cases=[
            TestCase(id="impatient_case",
                     persona=PersonaSpec(type="impatient"),
                     script=[Turn(user_says="x")]),
            TestCase(id="plain_case", script=[Turn(user_says="y")]),
        ],
    )
    result = asyncio.run(run_suite(suite, concurrency=1))
    # Plain case must not appear in the persona breakdown; impatient must.
    assert "impatient" in result.cost_by_persona
    assert "plain_case" not in result.cost_by_persona
    assert result.cost_by_persona["impatient"]["cases"] == 1


def test_jinja_prompt_renders_for_each_persona() -> None:
    for ptype in ("impatient", "accented", "code_switching", "kb_probing"):
        profile = get_profile(ptype)
        rendered = _render_prompt(profile, "AGENT: hello\nYOU: hi")
        # All built-in templates must contain the persona-specific marker.
        assert "PERSONA" in rendered.upper()
        assert "AGENT: hello" in rendered
        # The persona type or its goal text should be present.
        assert ptype.split("_")[0].lower() in rendered.lower() or \
               profile.goal[:20].lower() in rendered.lower()
