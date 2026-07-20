from __future__ import annotations

import logging
import os
from typing import Any

import numpy as np
import pandas as pd

from astock_alpha.data.benchmarks import BenchmarkStore
from astock_alpha.modules.base import StrategyModule
from astock_alpha.modules.m1_regime.classify import (
    RegimeStateMachine,
    above_ma60,
    classify_index_raw,
    combine_raw,
)
from astock_alpha.modules.m1_regime.sentiment import (
    LimitBoardRecord,
    SentimentGates,
    SentimentRollingWindow,
    evaluate_sentiment,
)
from astock_alpha.types import PipelineState, Regime

logger = logging.getLogger(__name__)

_ABNORMAL_RET_THRESHOLD = 0.10
_BREADTH_MISSING_DISCOUNT = 0.7
_MA_WARMUP_MULTIPLIER = 0.3
_SIDEWAYS_LOWVOL_FACTOR = 0.6
_SIDEWAYS_HIGHVOL_FACTOR = 0.3
_SENTIMENT_TIGHTEN_MULT = 0.5
_SENTIMENT_CAUTIOUS_MULT = 0.2


def _sanitize_close_series(
    series: pd.Series, *, label: str
) -> tuple[pd.Series, list[str]]:
    """去重 date、剔除 NaN；异常涨跌幅告警但不阻断。"""
    warnings: list[str] = []
    if series is None or series.empty:
        return pd.Series(dtype=float), warnings

    s = series.copy()
    s.index = pd.Index(s.index)
    # 去重：保留最后一条
    if s.index.has_duplicates:
        n_dup = int(s.index.duplicated().sum())
        s = s[~s.index.duplicated(keep="last")]
        warnings.append(f"m1_regime: {label} dropped {n_dup} duplicate dates")

    before = len(s)
    s = s.dropna().astype(float)
    if len(s) < before:
        warnings.append(
            f"m1_regime: {label} dropped {before - len(s)} NaN closes"
        )

    s = s.sort_index()
    if len(s) >= 2:
        rets = s.pct_change()
        abnormal = rets[rets.abs() > _ABNORMAL_RET_THRESHOLD].dropna()
        if len(abnormal) > 0:
            msg = (
                f"m1_regime: {label} abnormal |ret|>{_ABNORMAL_RET_THRESHOLD:.0%} "
                f"on {len(abnormal)} days (warn only)"
            )
            warnings.append(msg)
            logger.warning(msg)

    return s, warnings


def _vol_percentile_20d(
    closes: pd.Series, *, hist_window: int = 252, vol_window: int = 20
) -> float | None:
    """过去 vol_window 日收益标准差在 hist_window 日历史上的分位秩 [0,1]。"""
    s = closes.dropna().astype(float)
    if len(s) < vol_window + 2:
        return None
    rets = s.pct_change().dropna()
    if len(rets) < vol_window:
        return None
    rolling_vol = rets.rolling(vol_window).std().dropna()
    if rolling_vol.empty:
        return None
    hist = rolling_vol.iloc[-hist_window:]
    current = float(hist.iloc[-1])
    if np.isnan(current):
        return None
    return float((hist.to_numpy() <= current).mean())


def _apply_sideways_vol_regime(
    regime: Regime,
    closes: pd.Series,
    base_mult: float,
) -> tuple[Regime, float, dict[str, Any]]:
    """SIDEWAYS 叠加 20 日波动率分位 → LOWVOL / HIGHVOL。"""
    meta: dict[str, Any] = {}
    if regime != Regime.SIDEWAYS:
        return regime, base_mult, meta

    pct = _vol_percentile_20d(closes)
    meta["vol20_percentile"] = pct
    if pct is None:
        meta["vol_regime_note"] = "vol_percentile_unavailable"
        return regime, base_mult, meta

    if pct < 0.50:
        return (
            Regime.SIDEWAYS_LOWVOL,
            base_mult * _SIDEWAYS_LOWVOL_FACTOR,
            {**meta, "vol_regime_note": "sideways_lowvol_x0.6"},
        )
    if pct > 0.80:
        return (
            Regime.SIDEWAYS_HIGHVOL,
            base_mult * _SIDEWAYS_HIGHVOL_FACTOR,
            {**meta, "vol_regime_note": "sideways_highvol_x0.3"},
        )
    meta["vol_regime_note"] = "sideways_midvol"
    return regime, base_mult, meta


class RegimeModule(StrategyModule):
    """Module 1: dual-index regime + confirmation + optional sentiment gates."""

    name = "regime"
    module_id = "m1_regime"

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        store: BenchmarkStore | None = None,
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
        self.min_hold_days = int(reg.get("min_hold_days", 2))
        self.enable_breadth = bool(reg.get("enable_breadth", False))
        self.breadth_missing_discount = float(
            reg.get("breadth_missing_discount", _BREADTH_MISSING_DISCOUNT)
        )

        # T 日收盘算区制 → T+1 生效；开发环境强制开启，回测可关
        lag_cfg = reg.get("regime_lag_enabled", True)
        self.regime_lag_enabled = bool(lag_cfg)
        env = str(
            (self.config or {}).get("env")
            or os.getenv("ASTOCK_ENV", "development")
        ).lower()
        if env in ("development", "dev", "local"):
            self.regime_lag_enabled = True

        self._state_machine = RegimeStateMachine(
            confirm_days=self.confirm_days,
            panic_recover_days=self.panic_recover_days,
            min_hold_days=self.min_hold_days,
        )
        self._sentiment_window = SentimentRollingWindow(
            window=int(reg.get("sentiment_quantile_window", 252))
        )
        self._last_valid_regime: Regime | None = None
        self._last_valid_multiplier: float | None = None

    def is_ready(self) -> bool:
        return self.store is not None and self.store.exists()

    def _fallback_last_valid(
        self, state: PipelineState, reason: str
    ) -> PipelineState:
        state.warnings.append(reason)
        logger.warning(reason)
        if self._last_valid_regime is not None:
            state.regime = self._last_valid_regime
            state.regime_multiplier = float(
                self._last_valid_multiplier
                if self._last_valid_multiplier is not None
                else 0.3
            )
            state.meta["regime_fallback"] = "last_valid"
            state.meta["regime_fallback_reason"] = reason
        else:
            state.regime = Regime.SIDEWAYS
            state.regime_multiplier = _MA_WARMUP_MULTIPLIER
            state.meta["regime_fallback"] = "default_sideways"
            state.meta["regime_fallback_reason"] = reason
        return state

    def _base_multiplier(self, regime: Regime) -> float:
        mult_map = (self.config or {}).get("regime_multiplier") or {}
        key = regime.value
        if key in mult_map:
            return float(mult_map[key])
        # vol 子类型未单独配置时回退到 sideways 基数（再由 vol 因子缩放）
        if regime in (Regime.SIDEWAYS_LOWVOL, Regime.SIDEWAYS_HIGHVOL):
            return float(mult_map.get("sideways", 0.5))
        return float(mult_map.get(key, 0.5))

    def run(self, state: PipelineState) -> PipelineState:
        audit: dict[str, Any] = {
            "regime_lag_enabled": self.regime_lag_enabled,
            "state_machine": {},
            "vol": {},
            "sentiment_clean": {},
            "data_validation": [],
        }

        if not self.is_ready():
            return self._fallback_last_valid(
                state, "m1_regime: benchmarks missing; fallback last valid / sideways"
            )

        assert self.store is not None
        try:
            hs, zz = self.store.closes_pair(state.asof)
        except Exception as exc:  # noqa: BLE001 — 数据损坏降级
            return self._fallback_last_valid(
                state, f"m1_regime: benchmark load failed: {exc}"
            )

        hs, w1 = _sanitize_close_series(hs, label="hs300")
        zz, w2 = _sanitize_close_series(zz, label="csi500")
        for w in w1 + w2:
            state.warnings.append(w)
            audit["data_validation"].append(w)

        if hs.empty or zz.empty:
            return self._fallback_last_valid(
                state, "m1_regime: empty index series after sanitize"
            )

        # 日期内连接取交集
        common = sorted(set(hs.index) & set(zz.index))
        if not common:
            return self._fallback_last_valid(
                state, "m1_regime: no overlapping index dates"
            )
        hs = hs.loc[common]
        zz = zz.loc[common]

        # 前 60 个交易日 MA 未就绪 → SIDEWAYS，仓位 0.3
        if len(common) < self.ma_window:
            state.regime = Regime.SIDEWAYS
            state.regime_multiplier = _MA_WARMUP_MULTIPLIER
            state.warnings.append(
                f"m1_regime: MA{self.ma_window} not ready "
                f"({len(common)} bars); sideways@0.3"
            )
            audit["state_machine"]["note"] = "ma_warmup"
            state.meta["m1_regime_audit"] = audit
            self._remember(state.regime, state.regime_multiplier)
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
                above_ma60(hs_s, self.ma_window)
                and above_ma60(zz_s, self.ma_window)
            )

        confirmed, sm_reasons = self._state_machine.walk(raw_list, above_list)
        regime_t = confirmed[-1]
        reason_t = sm_reasons[-1] if sm_reasons else ""

        # 未来函数防护：T 日收盘计算 → T+1 生效
        if self.regime_lag_enabled:
            if len(confirmed) >= 2:
                regime = confirmed[-2]
                reason_eff = sm_reasons[-2] if len(sm_reasons) >= 2 else reason_t
            else:
                regime = Regime.SIDEWAYS
                reason_eff = "lag_warmup_sideways"
            audit["state_machine"]["computed_t"] = regime_t.value
            audit["state_machine"]["effective_t_plus_1"] = regime.value
            audit["state_machine"]["lag"] = 1
        else:
            regime = regime_t
            reason_eff = reason_t
            audit["state_machine"]["computed_t"] = regime_t.value
            audit["state_machine"]["effective_t_plus_1"] = regime.value
            audit["state_machine"]["lag"] = 0
            state.warnings.append(
                "m1_regime: regime_lag_enabled=False (look-ahead risk in live/dev)"
            )

        audit["state_machine"]["trigger_reason"] = reason_eff
        audit["state_machine"]["last_reasons"] = sm_reasons[-5:]

        base_mult = self._base_multiplier(regime)
        # 波动率维度（对生效区制为 SIDEWAYS 时细分）
        regime, multiplier, vol_meta = _apply_sideways_vol_regime(
            regime, hs, base_mult
        )
        audit["vol"] = vol_meta

        # 情绪 / breadth
        sentiment = self._sentiment(state)
        breadth_missing = self._breadth_missing(sentiment)
        if breadth_missing:
            multiplier = multiplier * self.breadth_missing_discount
            audit["breadth_missing_discount"] = self.breadth_missing_discount
            state.warnings.append(
                f"m1_regime: breadth missing → multiplier×{self.breadth_missing_discount}"
            )

        # 情绪条件叠加：取所有触发条件中的最小乘数（非连乘）
        candidates = [multiplier]
        if sentiment.tighten_position and regime != Regime.PANIC:
            candidates.append(_SENTIMENT_TIGHTEN_MULT)
        if sentiment.cautious_mode and regime != Regime.PANIC:
            candidates.append(_SENTIMENT_CAUTIOUS_MULT)
        multiplier = float(min(candidates))
        audit["sentiment_mult_candidates"] = candidates
        audit["sentiment_mult_min"] = multiplier
        audit["sentiment_clean"] = {
            "cleaned_limit_up_count": sentiment.cleaned_limit_up_count,
            "cleaned_limit_down_count": sentiment.cleaned_limit_down_count,
            "limit_up_ratio": sentiment.limit_up_ratio,
            "limit_down_ratio": sentiment.limit_down_ratio,
            "limit_up_ratio_zscore": sentiment.limit_up_ratio_zscore,
            "limit_down_ratio_zscore": sentiment.limit_down_ratio_zscore,
            "clean_stats": (sentiment.meta or {}).get("clean_stats") or {},
            "notes": sentiment.notes or [],
        }

        if sentiment.forbid_new_entries:
            state.meta["forbid_new_entries"] = True

        # state.regime 代表 T+1 仓位乘数对应的区制
        state.regime = regime
        state.regime_multiplier = multiplier
        state.meta["regime_raw_hs300"] = hs_raw_last.value
        state.meta["regime_raw_csi500"] = zz_raw_last.value
        state.meta["regime_raw_combined"] = raw_list[-1].value
        state.meta["regime_confirmed"] = regime_t.value
        state.meta["regime_effective"] = regime.value
        state.meta["regime_asof_index"] = str(common[-1])
        state.meta["regime_lag_enabled"] = self.regime_lag_enabled
        state.meta["m1_regime_audit"] = audit
        state.meta["sentiment"] = {
            "forbid_new_entries": sentiment.forbid_new_entries,
            "forbid_short_strategies": sentiment.forbid_short_strategies,
            "forbid_chase": sentiment.forbid_chase,
            "cautious_mode": sentiment.cautious_mode,
            "tighten_position": sentiment.tighten_position,
            "limit_up_ratio": sentiment.limit_up_ratio,
            "limit_down_ratio": sentiment.limit_down_ratio,
            "limit_up_ratio_zscore": sentiment.limit_up_ratio_zscore,
            "limit_down_ratio_zscore": sentiment.limit_down_ratio_zscore,
            "cleaned_limit_up_count": sentiment.cleaned_limit_up_count,
            "cleaned_limit_down_count": sentiment.cleaned_limit_down_count,
            "notes": sentiment.notes or [],
            "breadth_enabled": self.enable_breadth,
            "breadth_missing": breadth_missing,
        }
        if common[-1] != state.asof:
            state.warnings.append(
                f"m1_regime: last common index date {common[-1]} != asof {state.asof}"
            )

        self._remember(state.regime, state.regime_multiplier)
        return state

    def _remember(self, regime: Regime, multiplier: float) -> None:
        self._last_valid_regime = regime
        self._last_valid_multiplier = multiplier

    def _breadth_missing(self, sentiment: SentimentGates) -> bool:
        if not self.enable_breadth:
            return True
        # 启用 breadth 但无有效占比/家数输入
        has_ratio = sentiment.limit_up_ratio is not None
        has_counts = (
            sentiment.cleaned_limit_up_count is not None
            or sentiment.limit_up_count is not None
        )
        return not (has_ratio or has_counts)

    def _sentiment(self, state: PipelineState) -> SentimentGates:
        if not self.enable_breadth:
            return evaluate_sentiment()
        inj = (state.meta or {}).get("sentiment_inputs") or {}
        boards_raw = inj.get("limit_boards")
        boards: list[LimitBoardRecord] | None = None
        if boards_raw:
            boards = []
            for item in boards_raw:
                if isinstance(item, LimitBoardRecord):
                    boards.append(item)
                elif isinstance(item, dict):
                    boards.append(LimitBoardRecord(**item))

        return evaluate_sentiment(
            advance_decline_ratio=inj.get("advance_decline_ratio"),
            limit_up_count=inj.get("limit_up_count"),
            limit_down_count=inj.get("limit_down_count"),
            first_board_open_premium=inj.get("first_board_open_premium"),
            max_limit_up_streak=inj.get("max_limit_up_streak"),
            panic_proxy_share=inj.get("panic_proxy_share"),
            total_tradable_symbols=inj.get("total_tradable_symbols"),
            limit_boards=boards,
            rolling_window=self._sentiment_window,
        )
