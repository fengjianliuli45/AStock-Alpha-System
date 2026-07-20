"""m3_universe — 点前股份池硬/软过滤。"""

from __future__ import annotations

from typing import Any

from astock_alpha.modules.base import StrategyModule
from astock_alpha.modules.m3_universe.filters import (
    UniverseFilterConfig,
    evaluate_stock,
)
from astock_alpha.modules.m3_universe.snapshots import SnapshotProvider
from astock_alpha.types import PipelineState


# ── 环境适配过滤条件 ─────────────────────────────────────


def _apply_environment_filter(
    passed_symbols: list[str],
    symbol_snaps: dict[str, Any],
    env_rating: str,
) -> list[str]:
    """根据大盘环境评级，对已通过硬过滤的股票做额外筛选。

    只在 passed_symbols 中筛选，不会回灌被硬过滤剔除的股票。
    无环境评级或未知评级：全部保留。
    字段缺失（None）时：放行该条件（不因此剔除）。
    """
    if not env_rating or not passed_symbols:
        return list(passed_symbols)

    result: list[str] = []
    for symbol in passed_symbols:
        snap = symbol_snaps.get(symbol)
        if snap is None:
            result.append(symbol)
            continue

        ok = True

        if env_rating == "BULL_STRONG":
            # 动量 + 成长 + 活跃
            if snap.momentum_20d is not None and snap.momentum_20d < 5.0:
                ok = False
            elif snap.avg_turnover_20d is not None and snap.avg_turnover_20d < 3.0:
                ok = False

        elif env_rating == "BULL_WEAK":
            # 估值合理 + ROE 质量
            if snap.roe_ttm is not None and snap.roe_ttm < 10.0:
                ok = False

        elif env_rating == "BEAR_WEAK":
            # 防御：低估值 + 稳定质量
            if snap.roe_ttm is not None and snap.roe_ttm < 5.0:
                ok = False

        elif env_rating == "BEAR_STRONG":
            # 极防御：仅保留大盘股
            if snap.total_market_cap is not None and snap.total_market_cap < 100e9:
                ok = False  # <1000亿 剔除

        if ok:
            result.append(symbol)

    return result


class UniverseModule(StrategyModule):
    """Module 3: PIT hard/soft universe filters + 环境评级适配。"""

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
        symbol_snaps: dict[str, Any] = {}

        for snap in snaps:
            symbol_snaps[snap.symbol] = snap
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

        # ── 环境适配过滤（只对已通过硬过滤的股票操作）──
        env = (state.meta.get("m2_environment") or {})
        env_rating = env.get("rating", "")
        if env_rating:
            env_filtered = _apply_environment_filter(passed, symbol_snaps, env_rating)
            if env_filtered:
                rejected_env = set(passed) - set(env_filtered)
                if rejected_env:
                    state.warnings.append(
                        f"m3_universe: env_filter({env_rating}) rejected "
                        f"{len(rejected_env)} stocks"
                    )
                state.universe = env_filtered
                state.meta["env_filter_rejected"] = len(rejected_env)
                state.meta["env_rating_applied"] = env_rating
            else:
                state.warnings.append(
                    f"m3_universe: env_filter({env_rating}) emptied universe; "
                    "falling back to unfiltered"
                )
                state.meta["env_filter_emptied"] = True

        state.meta["universe_input_size"] = len(snaps)
        state.meta["universe_size"] = len(passed)
        state.meta["universe_reject_counts"] = reject_counts
        state.meta["universe_incomplete"] = sorted(incomplete_set)
        state.meta["universe_details"] = details
        return state
