"""Cost-ceiling tracker for ``voxeval run --max-cost N``.

The tracker is async-safe and only resists when ``try_spend`` is called.
Anything that pays for itself (LLM judge calls, persona-LLM turns, KB
generation) consults it before incurring the cost; if the spend would
exceed the ceiling, the caller is expected to mark its result as
``skipped_budget`` rather than blowing past the limit.

The default per-judge estimate (1500 prompt + 80 completion tokens at
gpt-4o-mini-2024-07-18 rates) is intentionally generous — the goal is
to STOP an out-of-control suite, not to bill-grade the run.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

# Estimated cost in USD for one judge round-trip (gpt-4o-mini snapshot).
# Update when the snapshot moves or when caching produces measurably
# different per-call accounting.
DEFAULT_JUDGE_COST_USD = 0.0003


@dataclass
class BudgetTracker:
    max_cost_usd: float | None = None          # None = unlimited
    spent_usd: float = 0.0
    skipped: int = 0
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def try_spend(self, amount_usd: float) -> bool:
        """Reserve ``amount_usd`` if there's room. Return True on success."""
        async with self._lock:
            if self.max_cost_usd is None:
                self.spent_usd += amount_usd
                return True
            if self.spent_usd + amount_usd > self.max_cost_usd:
                self.skipped += 1
                return False
            self.spent_usd += amount_usd
            return True

    def try_spend_sync(self, amount_usd: float) -> bool:
        """Sync variant — safe because BudgetTracker is mutated only on the
        event loop thread in v0.1. Used inside assertion evaluators which
        are not async."""
        if self.max_cost_usd is None:
            self.spent_usd += amount_usd
            return True
        if self.spent_usd + amount_usd > self.max_cost_usd:
            self.skipped += 1
            return False
        self.spent_usd += amount_usd
        return True

    @property
    def remaining_usd(self) -> float | None:
        if self.max_cost_usd is None:
            return None
        return max(0.0, self.max_cost_usd - self.spent_usd)
