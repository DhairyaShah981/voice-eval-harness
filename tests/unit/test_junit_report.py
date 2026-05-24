"""JUnit XML reporter produces well-formed XML with failure entries."""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

from voice_eval_harness.core.models import (
    AssertionResult,
    RunResult,
    SuiteResult,
)
from voice_eval_harness.report.junit import write_junit


def test_junit_passing_and_failing(tmp_path: Path) -> None:
    suite = SuiteResult(
        cases=[
            RunResult(case_id="ok_one", passed=True, duration_ms=120,
                      assertion_results=[AssertionResult(kind="contains", passed=True)]),
            RunResult(case_id="boom", passed=False, duration_ms=80,
                      error="connector exploded",
                      assertion_results=[
                          AssertionResult(kind="no_crash", passed=False,
                                          detail="disconnect=error"),
                      ]),
        ],
    )
    out = tmp_path / "report.xml"
    write_junit(suite, out)

    tree = ET.fromstring(out.read_bytes())
    assert tree.tag == "testsuite"
    assert tree.attrib["tests"] == "2"
    assert tree.attrib["failures"] == "1"
    cases = tree.findall("testcase")
    assert len(cases) == 2
    assert cases[0].attrib["name"] == "ok_one"
    assert cases[0].find("failure") is None
    failure = cases[1].find("failure")
    assert failure is not None
    assert "exploded" in (failure.text or "")
