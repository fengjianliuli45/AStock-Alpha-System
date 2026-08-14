from __future__ import annotations

from datetime import date
from typing import Any

from astock_alpha.data.benchmarks import BenchmarkStore
from astock_alpha.modules.base import StrategyModule
from astock_alpha.modules.m1_regime.classify import (
    above_ma60,
    classify_index_raw,
    combine_raw,
    walk_confirmed_regimes,
)
from astock_alpha.modules.m1_regime.sentiment import SentimentGates, evaluate_sentiment
from astock_alpha.types import PipelineState, Regime


class RegimeModule(StrategyModule):
    """Module 1: dual-index regime + confirmation + optional sentiment gates."""

    name = "regime"
    module_id = "m1_regime"

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        store: BenchmarkStore | Any | None = None,
    ) -> None:
        super().__init__(config)
        data = (self.config or {}).get("data") or {}
        root = data.get("benchmarks_root")
        self.store = store or (BenchmarkStore(root) if root else None)
        reg = (self.config or {}).get("regime") or {}
        self.ma_window = int(reg.get("ma_window", 60))
        self.sideways_band = float(reg.get("sideways_band", 0.03))
        self.slope_lookback = int(reg.get("slope_lookback", 5))
        self.confirm_days = int(reg.get("confirm_days", 2))
        self.panic_day_drop = float(reg.get("panic_day_drop", 0.05))
        self.panic_5d_drop = float(reg.get("panic_5d_drop", 0.10))
        self.panic_recover_days = int(reg.get("panic_recover_days", 3))
        self.enable_breadth = bool(reg.get("enable_breadth", False))

    def is_ready(self) -> bool:
        return self.store is not None and self.store.exists()

    def run(self, state: PipelineState) -> PipelineState:
        if not self.is_ready():
            state.warnings.append("m1_regime: benchmarks missing; default sideways")
            state.regime = Regime.SIDEWAYS
            state.regime_multiplier = float(
                (self.config or {}).get("regime_multiplier", {}).get("sideways", 0.5)
            )
            return state

        assert self.store is not None
        hs, zz = self.store.closes_pair(state.asof)
        if hs.empty or zz.empty:
            state.warnings.append("m1_regime: empty index series")
            state.regime = Regime.SIDEWAYS
            state.regime_multiplier = 0.5
            return state

        # Align calendar to intersection of both indexes
        common = sorted(set(hs.index) & set(zz.index))
        if not common:
            state.warnings.append("m1_regime: no overlapping index dates")
            state.regime = Regime.SIDEWAYS
            state.regime_multiplier = 0.5
            return state

        raw_list: list[Regime] = []
        above_list: list[bool] = []
        hs_raw_last = Regime.SIDEWAYS
        zz_raw_last = Regime.SIDEWAYS
        for d in common:
            hs_s = hs.loc[:d]
            zz_s = zz.loc[:d]
            hs_raw = classify_index_raw(
                hs_s,
                ma_window=self.ma_window,
                sideways_band=self.sideways_band,
                slope_lookback=self.slope_lookback,
                panic_day_drop=self.panic_day_drop,
                panic_5d_drop=self.panic_5d_drop,
            )
            zz_raw = classify_index_raw(
                zz_s,
                ma_window=self.ma_window,
                sideways_band=self.sideways_band,
                slope_lookback=self.slope_lookback,
                panic_day_drop=self.panic_day_drop,
                panic_5d_drop=self.panic_5d_drop,
            )
            hs_raw_last, zz_raw_last = hs_raw, zz_raw
            raw_list.append(combine_raw(hs_raw, zz_raw))
            above_list.append(
                above_ma60(hs_s, self.ma_window) and above_ma60(zz_s, self.ma_window)
            )

        confirmed = walk_confirmed_regimes(
            raw_list,
            above_list,
            confirm_days=self.confirm_days,
            panic_recover_days=self.panic_recover_days,
        )
        regime = confirmed[-1]
        mult_map = (self.config or {}).get("regime_multiplier") or {}
        multiplier = float(mult_map.get(regime.value, 0.5))

        sentiment = self._sentiment(state)
        if sentiment.tighten_position and regime != Regime.PANIC:
            multiplier = min(multiplier, 0.5)
        if sentiment.cautious_mode and regime != Regime.PANIC:
            multiplier = min(multiplier, 0.2)
        if sentiment.forbid_new_entries:
            state.meta["forbid_new_entries"] = True

        state.regime = regime
        state.regime_multiplier = multiplier
        state.meta["regime_raw_hs300"] = hs_raw_last.value
        state.meta["regime_raw_csi500"] = zz_raw_last.value
        state.meta["regime_raw_combined"] = raw_list[-1].value
        state.meta["regime_confirmed"] = regime.value
        state.meta["regime_asof_index"] = str(common[-1])
        state.meta["sentiment"] = {
            "forbid_new_entries": sentiment.forbid_new_entries,
            "forbid_short_strategies": sentiment.forbid_short_strategies,
            "forbid_chase": sentiment.forbid_chase,
            "cautious_mode": sentiment.cautious_mode,
            "tighten_position": sentiment.tighten_position,
            "notes": sentiment.notes or [],
            "breadth_enabled": self.enable_breadth,
        }
        if common[-1] != state.asof:
            state.warnings.append(
                f"m1_regime: last common index date {common[-1]} != asof {state.asof}"
            )
        return state

    def _sentiment(self, state: PipelineState) -> SentimentGates:
        if not self.enable_breadth:
            return evaluate_sentiment()  # no gates without breadth inputs
        # Breadth computation from full market is deferred; allow meta injection for tests.
        inj = (state.meta or {}).get("sentiment_inputs") or {}
        return evaluate_sentiment(
            advance_decline_ratio=inj.get("advance_decline_ratio"),
            limit_up_count=inj.get("limit_up_count"),
            limit_down_count=inj.get("limit_down_count"),
            first_board_open_premium=inj.get("first_board_open_premium"),
            max_limit_up_streak=inj.get("max_limit_up_streak"),
            panic_proxy_share=inj.get("panic_proxy_share"),
        )
