"""JUnit XML reporter — drop-in for GitHub Actions / CircleCI / etc."""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

from voice_eval_harness.core.models import SuiteResult


def write_junit(result: SuiteResult, path: Path) -> None:
    suite = ET.Element("testsuite", {
        "name": "voxeval",
        "tests": str(len(result.cases)),
        "failures": str(result.failed),
        "errors": "0",
        "time": f"{sum(c.duration_ms for c in result.cases) / 1000:.3f}",
    })
    for case in result.cases:
        tc = ET.SubElement(suite, "testcase", {
            "name": case.case_id,
            "classname": "voxeval",
            "time": f"{case.duration_ms / 1000:.3f}",
        })
        if not case.passed:
            fail_msgs: list[str] = []
            if case.error:
                fail_msgs.append(case.error)
            for ar in case.assertion_results:
                if not ar.passed:
                    fail_msgs.append(f"{ar.kind}: {ar.detail or 'failed'}")
            failure = ET.SubElement(tc, "failure", {
                "message": fail_msgs[0] if fail_msgs else "case failed",
                "type": "AssertionFailure",
            })
            failure.text = "\n".join(fail_msgs)
    tree = ET.ElementTree(suite)
    ET.indent(tree, "  ")
    path.write_bytes(ET.tostring(suite, encoding="utf-8", xml_declaration=True))
