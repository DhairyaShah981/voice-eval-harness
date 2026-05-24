"""Retell agent JSON linter rules.

The full rule set is ported from ``trifetch-voice-service/scripts/validate_retell_agent.py``
(13 checks born from real production import failures), plus two new rules
specific to the voice-eval-harness:

  RTL-014  — ngrok host-string scan (dev tunnels rot in production)
  RTL-015  — KB empty but referenced in global prompt

A vendored copy of the legacy validator lives at
``voice_eval_harness/_vendor/validate_retell_agent.py`` and is used by
``tests/test_linter_parity.py`` to guarantee these rules agree with the
source-of-truth on every fixture.
"""

from __future__ import annotations

from voice_eval_harness.linters.base import Rule
from voice_eval_harness.linters.retell import rules as _rules

RETELL_RULES: list[Rule] = _rules.ALL_RULES

__all__ = ["RETELL_RULES"]
