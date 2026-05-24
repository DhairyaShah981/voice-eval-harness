"""Orchestrator that runs a list of Rules against one agent JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from voice_eval_harness.linters.base import Report, Rule


def lint_agent(agent: dict[str, Any], rules: list[Rule]) -> Report:
    """Run every rule against the agent dict and collect issues."""
    report = Report(rules_run=[r.id for r in rules])
    for rule in rules:
        try:
            report.issues.extend(rule.check(agent))
        except Exception as exc:  # noqa: BLE001 — rule bugs shouldn't kill the run
            from voice_eval_harness.linters.base import Issue, Severity
            report.issues.append(Issue(
                rule.id, Severity.WARNING, "<rule-error>",
                f"rule raised {type(exc).__name__}: {exc}",
            ))
    return report


def lint_file(path: str | Path, rules: list[Rule]) -> Report:
    """Load JSON from disk and lint it."""
    path = Path(path)
    text = path.read_text()
    try:
        agent = json.loads(text)
    except json.JSONDecodeError as exc:
        from voice_eval_harness.linters.base import Issue, Severity
        report = Report(rules_run=[r.id for r in rules])
        report.issues.append(Issue(
            "RTL-000", Severity.FATAL, str(path),
            f"file is not valid JSON: {exc}",
        ))
        return report
    return lint_agent(agent, rules)
