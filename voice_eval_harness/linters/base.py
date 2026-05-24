"""Linter primitives — Severity, Issue, Rule, and the registry helper.

A linter Rule looks at an agent JSON dict and yields zero or more Issues.
Rules are pure (no I/O, no LLM calls) so they run in milliseconds and can
be wired into pre-commit hooks and CI without any API keys.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Severity(str, Enum):
    FATAL = "fatal"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True)
class Issue:
    rule_id: str
    severity: Severity
    path: str            # JSONPath-ish location of the offending value
    message: str         # short, human-readable
    fix_hint: str = ""   # optional one-liner on how to fix

    def render(self) -> str:
        glyph = {"fatal": "❌", "warning": "⚠️ ", "info": "ℹ️ "}[self.severity.value]
        line = f"  {glyph} [{self.rule_id}] {self.path}: {self.message}"
        if self.fix_hint:
            line += f"\n        ↳ {self.fix_hint}"
        return line


class Rule(ABC):
    """Subclass and implement ``check``. Rules are instantiated once and reused."""

    id: str = ""
    severity: Severity = Severity.FATAL
    title: str = ""

    @abstractmethod
    def check(self, agent: dict[str, Any]) -> list[Issue]: ...


@dataclass
class Report:
    rules_run: list[str] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)

    @property
    def fatals(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == Severity.FATAL]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == Severity.WARNING]

    @property
    def ok(self) -> bool:
        return not self.fatals
