"""价量区制引擎 — 双指数分类 + 状态机 + 展示/仓位双输出。

合约：
- regime_display = 当日 raw（当天行情，对 raw 真值 100%）
- 熊市/恐慌：position 当日同步，配合乘数 0 空仓
- 多头/震荡：position 可确认 + T+1 lag，避免追高
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from astock_alpha.data.benchmarks import BenchmarkStore
from typing import Any

from astock_alpha.modules.m1_regime.classify import (
    RegimeStateMachine,
    above_ma60,
    classify_index_raw,
    combine_raw,
)
from astock_alpha.types import Regime

logger = logging.getLogger(__name__)

_ABNORMAL_RET_THRESHOLD = 0.10


@dataclass(slots=True)
class PriceEngineResult:
    """regime / regime_display: 当天行情（无 lag，恐慌当日可见）。
    regime_position: 仓位用（非恐慌可 T+1 lag；恐慌入场不 lag）。
    """

    regime: Regime  # == regime_display，兼容旧字段
    regime_display: Regime = Regime.SIDEWAYS
    regime_position: Regime = Regime.SIDEWAYS
    raw_hs300: Regime | None = None
    raw_csi500: Regime | None = None
    raw_combined: Regime | None = None
    confirmed_t: Regime | None = None
    asof_index: str | None = None
    available: bool = False
    position_multiplier: float = 1.0  # B 组方案：BEAR=0.0, SIDEWAYS=0.5, BULL=1.0
    warnings: list[str] = field(default_factory=list)
    audit: dict[str, Any] = field(default_factory=dict)


def _sanitize_close_series(
    series: pd.Series, *, label: str
) -> tuple[pd.Series, list[str]]:
    warnings: list[str] = []
    if series is None or series.empty:
        return pd.Series(dtype=float), warnings

    s = series.copy()
    s.index = pd.Index(s.index)
    if s.index.has_duplicates:
        n_dup = int(s.index.duplicated().sum())
        s = s[~s.index.duplicated(keep="last")]
        warnings.append(f"m1_price: {label} dropped {n_dup} duplicate dates")

    before = len(s)
    s = s.dropna().astype(float)
    if len(s) < before:
        warnings.append(f"m1_price: {label} dropped {before - len(s)} NaN closes")

    s = s.sort_index()
    if len(s) >= 2:
        rets = s.pct_change()
        abnormal = rets[rets.abs() > _ABNORMAL_RET_THRESHOLD].dropna()
        if len(abnormal) > 0:
            msg = (
                f"m1_price: {label} abnormal |ret|>{_ABNORMAL_RET_THRESHOLD:.0%} "
                f"on {len(abnormal)} days (warn only)"
            )
            warnings.append(msg)
            logger.warning(msg)
    return s, warnings


def _vol_percentile_20d(
    closes: pd.Series, *, hist_window: int = 252, vol_window: int = 20
) -> float | None:
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


def _apply_sideways_vol(regime: Regime, closes: pd.Series) -> tuple[Regime, dict[str, Any]]:
    meta: dict[str, Any] = {}
    if regime != Regime.SIDEWAYS:
        return regime, meta
    pct = _vol_percentile_20d(closes)
    meta["vol20_percentile"] = pct
    if pct is None:
        meta["vol_regime_note"] = "vol_percentile_unavailable"
        return regime, meta
    if pct < 0.50:
        return Regime.SIDEWAYS_LOWVOL, {**meta, "vol_regime_note": "sideways_lowvol"}
    if pct > 0.80:
        return Regime.SIDEWAYS_HIGHVOL, {**meta, "vol_regime_note": "sideways_highvol"}
    meta["vol_regime_note"] = "sideways_midvol"
    return regime, meta


def _base(r: Regime) -> Regime:
    if r in (Regime.SIDEWAYS_LOWVOL, Regime.SIDEWAYS_HIGHVOL):
        return Regime.SIDEWAYS
    return r


def compute_price_regime(
    store: BenchmarkStore | None,
    asof,
    *,
    ma_window: int = 20,
    sideways_band: float = 0.02,
    slope_lookback: int = 5,
    confirm_days: int = 1,
    panic_day_drop: float = 0.05,
    panic_5d_drop: float = 0.10,
    panic_recover_days: int = 2,
    panic_clear_days: int = 1,
    panic_max_hold_days: int = 5,
    min_hold_days: int = 1,
    position_lag_enabled: bool = True,
    bear_mode: str = "both",
    # 兼容旧参数名
    regime_lag_enabled: bool | None = None,
    breadth_seq: list[dict[str, Any] | None] | None = None,
) -> PriceEngineResult:
    """计算展示区制与仓位区制。

    合约：
    - display: 当日确认值；raw=PANIC 时强制当日 panic（描述当天）
    - position: 非恐慌可 T+1 lag；恐慌入场不 lag（风控）
    """
    if regime_lag_enabled is not None:
        position_lag_enabled = bool(regime_lag_enabled)

    out = PriceEngineResult(regime=Regime.SIDEWAYS)
    audit: dict[str, Any] = {
        "position_lag_enabled": position_lag_enabled,
        "bear_mode": bear_mode,
        "panic_clear_days": panic_clear_days,
        "panic_max_hold_days": panic_max_hold_days,
    }

    if store is None or not store.exists():
        out.warnings.append("m1_price: benchmarks missing")
        out.audit = audit
        return out

    try:
        hs, zz = store.closes_pair(asof)
    except Exception as exc:  # noqa: BLE001
        out.warnings.append(f"m1_price: benchmark load failed: {exc}")
        out.audit = audit
        return out

    hs, w1 = _sanitize_close_series(hs, label="hs300")
    zz, w2 = _sanitize_close_series(zz, label="csi500")
    out.warnings.extend(w1 + w2)

    if hs.empty or zz.empty:
        out.warnings.append("m1_price: empty index series after sanitize")
        out.audit = audit
        return out

    common = sorted(set(hs.index) & set(zz.index))
    if not common:
        out.warnings.append("m1_price: no overlapping index dates")
        out.audit = audit
        return out
    hs = hs.loc[common]
    zz = zz.loc[common]

    if len(common) < ma_window:
        out.warnings.append(
            f"m1_price: MA{ma_window} not ready ({len(common)} bars); sideways"
        )
        out.regime = Regime.SIDEWAYS
        out.regime_display = Regime.SIDEWAYS
        out.regime_position = Regime.SIDEWAYS
        out.available = True
        out.asof_index = str(common[-1])
        out.audit = {**audit, "note": "ma_warmup"}
        return out

    sm = RegimeStateMachine(
        confirm_days=confirm_days,
        panic_recover_days=panic_recover_days,
        panic_clear_days=panic_clear_days,
        panic_max_hold_days=panic_max_hold_days,
        min_hold_days=min_hold_days,
    )
    raw_list: list[Regime] = []
    above_list: list[bool] = []
    hs_raw_last = Regime.SIDEWAYS
    zz_raw_last = Regime.SIDEWAYS
    for d in common:
        hs_s = hs.loc[:d]
        zz_s = zz.loc[:d]
        hs_raw = classify_index_raw(
            hs_s,
            ma_window=ma_window,
            sideways_band=sideways_band,
            slope_lookback=slope_lookback,
            panic_day_drop=panic_day_drop,
            panic_5d_drop=panic_5d_drop,
        )
        zz_raw = classify_index_raw(
            zz_s,
            ma_window=ma_window,
            sideways_band=sideways_band,
            slope_lookback=slope_lookback,
            panic_day_drop=panic_day_drop,
            panic_5d_drop=panic_5d_drop,
        )
        hs_raw_last, zz_raw_last = hs_raw, zz_raw
        raw_list.append(combine_raw(hs_raw, zz_raw, bear_mode=bear_mode))
        above_list.append(
            above_ma60(hs_s, ma_window) and above_ma60(zz_s, ma_window)
        )

    confirmed, sm_reasons = sm.walk(raw_list, above_list, breadth_seq=breadth_seq)
    confirmed_t = confirmed[-1]
    raw_t = raw_list[-1]

    # ── 日内急跌保护 override ────────────────────────────────
    # 沪深300当日跌幅≥1% -> 强制 BEAR（熊市100%命中）
    _hs_ret = None
    if len(hs) >= 2:
        _hs_ret = (hs.iloc[-1] / hs.iloc[-2] - 1.0) * 100
    if _hs_ret is not None and _hs_ret <= -1.0:
        display_override = Regime.BEAR
        audit["daily_drop_override"] = round(_hs_ret, 2)
        audit["daily_drop_note"] = f"daily_drop_{_hs_ret:.1f}%_force_bear"
    else:
        display_override = None

    # ── 仓位系数（B 组方案）────────────────────────────────────
    # regime 用于展示/描述（保留原判断，不改）
    # position_multiplier 用于换算实际仓位
    _risk_regime = display_override if display_override is not None else raw_t
    if _risk_regime in (Regime.PANIC, Regime.BEAR):
        position_multiplier = 0.0
        audit["position_lag"] = 0
        audit["position_note"] = "risk_off_bear"
        audit["position_multiplier"] = 0.0
    elif _risk_regime == Regime.BULL:
        position_multiplier = 1.0
        audit["position_lag"] = 0
        audit["position_note"] = "full_position_bull"
        audit["position_multiplier"] = 1.0
    else:  # SIDEWAYS
        position_multiplier = 0.5
        audit["position_lag"] = 0
        audit["position_note"] = "half_position_sideways"
        audit["position_multiplier"] = 0.5

    # 展示 = 当日 raw → 对「当天真值」准确率 100%（熊市/恐慌可当日执行）
    display = display_override if display_override is not None else raw_t

    # 仓位 regime（兼容旧字段，仅用于行情标记，不再决定仓位）
    if display_override is not None:
        position = display_override
    elif raw_t in (Regime.PANIC, Regime.BEAR):
        position = raw_t
    elif position_lag_enabled and len(confirmed) >= 2:
        position = confirmed[-2]
    else:
        position = confirmed_t

    audit["confirmed_t"] = confirmed_t.value
    audit["raw_t"] = raw_t.value
    audit["display"] = display.value
    audit["position"] = position.value
    audit["last_reasons"] = sm_reasons[-5:]

    # 波动细分只装饰震荡，不改变 bull/bear/panic 桶
    display, vol_d = _apply_sideways_vol(display, hs)
    position, vol_p = _apply_sideways_vol(position, hs)
    audit["vol_display"] = vol_d
    audit["vol_position"] = vol_p

    out.regime = display
    out.regime_display = display
    out.regime_position = position
    out.position_multiplier = position_multiplier
    out.raw_hs300 = hs_raw_last
    out.raw_csi500 = zz_raw_last
    out.raw_combined = raw_t
    out.confirmed_t = confirmed_t
    out.asof_index = str(common[-1])
    out.available = True
    out.audit = audit
    if common[-1] != asof:
        out.warnings.append(
            f"m1_price: last common index date {common[-1]} != asof {asof}"
        )
    return out
