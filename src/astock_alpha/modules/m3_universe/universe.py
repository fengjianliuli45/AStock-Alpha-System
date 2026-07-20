from __future__ import annotations

from typing import Any

from astock_alpha.modules.base import StrategyModule
from astock_alpha.modules.m3_universe.filters import (
    UniverseFilterConfig,
    evaluate_stock,
)
from astock_alpha.modules.m3_universe.snapshots import SnapshotProvider
from astock_alpha.types import PipelineState


# ── 环境适配过滤条件 ───────────────────────────────────────────


def _apply_environment_filter(
    snaps: list[Any],
    env_rating: str,
) -> list[str]:
    """根据大盘环境评级，对已通过硬过滤的股票做额外筛选。

    无环境评级或未知评级：不过滤，全部保留。
    """
    if not env_rating:
        return [s.symbol for s in snaps]

    passed: list[str] = []
    for snap in snaps:
        symbol = snap.symbol

        if env_rating == "BULL_STRONG":
            # 动量 + 成长 + 活跃
            ok = True
            if snap.momentum_20d is not None and snap.momentum_20d < 5.0:
                ok = False  # 近20日涨幅<5% 剔除
            elif snap.avg_turnover_20d is not None and snap.avg_turnover_20d < 3.0:
                ok = False  # 近20日换手率<3% 剔除
            if not ok:
                continue

        elif env_rating == "BULL_WEAK":
            # 估值合理 + ROE 质量
            ok = True
            if snap.roe_ttm is not None and snap.roe_ttm < 10.0:
                ok = False
            if not ok:
                continue

        elif env_rating == "BEAR_WEAK":
            # 防御：低贝塔 + 低估值 + 稳定分红
            ok = True
            if snap.roe_ttm is not None and snap.roe_ttm < 5.0:
                ok = False
            if not ok:
                continue

        elif env_rating == "BEAR_STRONG":
            # 极防御：仅保留上证50/沪深300成分股（通过配置或大盘市值）
            ok = True
            if snap.total_market_cap is not None and snap.total_market_cap < 100e9:
                ok = False  # <1000亿 剔除
            if not ok:
                continue

        passed.append(symbol)

    return passed


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

        # ── 环境适配过滤 ──
        env = (state.meta.get("m2_environment") or {})
        env_rating = env.get("rating", "")
        if env_rating:
            env_filtered = _apply_environment_filter(snaps, env_rating)
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
