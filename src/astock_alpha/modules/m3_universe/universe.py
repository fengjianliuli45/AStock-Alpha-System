from __future__ import annotations

from typing import Any

from astock_alpha.modules.base import StrategyModule
from astock_alpha.modules.m3_universe.filters import (
    UniverseFilterConfig,
    evaluate_stock,
)
from astock_alpha.modules.m3_universe.snapshots import SnapshotProvider
from astock_alpha.types import PipelineState


class UniverseModule(StrategyModule):
    """Module 3: PIT hard/soft universe filters (design v1.0)."""

    name = "universe"
    module_id = "m3_universe"

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        provider: SnapshotProvider | None = None,
    ) -> None:
        super().__init__(config)
        self.filter_cfg = UniverseFilterConfig.from_strategy_config(self.config)
        self.provider = provider

    def is_ready(self) -> bool:
        return self.provider is not None

    def run(self, state: PipelineState) -> PipelineState:
        if self.provider is None:
            state.warnings.append(
                "m3_universe: no SnapshotProvider; universe left empty (wire data adapter)"
            )
            state.universe = []
            state.meta["universe_reject_counts"] = {}
            state.meta["universe_incomplete"] = ["provider_missing"]
            return state

        seed = state.universe or None
        snaps = self.provider.load(state.asof, seed)
        passed: list[str] = []
        reject_counts: dict[str, int] = {}
        incomplete_set: set[str] = set()
        details: dict[str, Any] = {}

        for snap in snaps:
            decision = evaluate_stock(snap, self.filter_cfg)
            incomplete_set.update(decision.incomplete_filters)
            if decision.passed:
                passed.append(snap.symbol)
            else:
                for reason in decision.reject_reasons:
                    reject_counts[reason] = reject_counts.get(reason, 0) + 1
            details[snap.symbol] = {
                "passed": decision.passed,
                "reject_reasons": decision.reject_reasons,
                "incomplete_filters": decision.incomplete_filters,
            }

        state.universe = passed
        state.incomplete_filters = sorted(incomplete_set)
        if incomplete_set:
            state.warnings.append(
                "m3_universe: incomplete filters "
                f"{sorted(incomplete_set)}; degraded but not halted"
            )
        state.meta["universe_input_size"] = len(snaps)
        state.meta["universe_size"] = len(passed)
        state.meta["universe_reject_counts"] = reject_counts
        state.meta["universe_incomplete"] = sorted(incomplete_set)
        state.meta["universe_details"] = details
        return state
