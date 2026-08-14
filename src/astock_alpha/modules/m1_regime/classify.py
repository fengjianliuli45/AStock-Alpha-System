from __future__ import annotations

import numpy as np
import pandas as pd

from astock_alpha.types import Regime


def _ma_slope_up(ma: pd.Series, lookback: int) -> bool:
    if len(ma) <= lookback:
        return False
    a = float(ma.iloc[-1])
    b = float(ma.iloc[-1 - lookback])
    if np.isnan(a) or np.isnan(b):
        return False
    return a > b


def _ma_slope_down(ma: pd.Series, lookback: int) -> bool:
    if len(ma) <= lookback:
        return False
    a = float(ma.iloc[-1])
    b = float(ma.iloc[-1 - lookback])
    if np.isnan(a) or np.isnan(b):
        return False
    return a < b


def classify_index_raw(
    closes: pd.Series,
    *,
    ma_window: int = 60,
    sideways_band: float = 0.03,
    slope_lookback: int = 5,
    panic_day_drop: float = 0.05,
    panic_5d_drop: float = 0.10,
) -> Regime:
    """Classify one index series ending at the last bar (asof)."""
    s = closes.dropna().astype(float)
    if len(s) < ma_window + slope_lookback + 1:
        return Regime.SIDEWAYS

    ma = s.rolling(ma_window).mean()
    close = float(s.iloc[-1])
    ma_now = float(ma.iloc[-1])
    if np.isnan(ma_now) or ma_now == 0:
        return Regime.SIDEWAYS

    day_ret = close / float(s.iloc[-2]) - 1.0 if len(s) >= 2 else 0.0
    ret_5d = close / float(s.iloc[-6]) - 1.0 if len(s) >= 6 else 0.0
    if day_ret <= -panic_day_drop or ret_5d <= -panic_5d_drop:
        return Regime.PANIC

    dist = close / ma_now - 1.0
    if abs(dist) <= sideways_band:
        return Regime.SIDEWAYS
    if close > ma_now and _ma_slope_up(ma, slope_lookback):
        return Regime.BULL
    if close < ma_now and _ma_slope_down(ma, slope_lookback):
        return Regime.BEAR
    return Regime.SIDEWAYS


def combine_raw(hs300: Regime, csi500: Regime) -> Regime:
    """Dual-index rule: panic wins; either bear → bear; both bull → bull; else sideways."""
    if hs300 == Regime.PANIC or csi500 == Regime.PANIC:
        return Regime.PANIC
    if hs300 == Regime.BEAR or csi500 == Regime.BEAR:
        return Regime.BEAR
    if hs300 == Regime.BULL and csi500 == Regime.BULL:
        return Regime.BULL
    return Regime.SIDEWAYS


def above_ma60(closes: pd.Series, ma_window: int = 60) -> bool:
    s = closes.dropna().astype(float)
    if len(s) < ma_window:
        return False
    ma = float(s.rolling(ma_window).mean().iloc[-1])
    close = float(s.iloc[-1])
    if np.isnan(ma):
        return False
    return close >= ma


def walk_confirmed_regimes(
    combined_raw: list[Regime],
    both_above_ma: list[bool],
    *,
    confirm_days: int = 2,
    panic_recover_days: int = 3,
) -> list[Regime]:
    """Apply confirmation / panic-recovery along a timeline."""
    if not combined_raw:
        return []
    confirmed: list[Regime] = [combined_raw[0]]
    pending: Regime | None = None
    pending_count = 0
    recover_streak = 0

    for i in range(1, len(combined_raw)):
        raw = combined_raw[i]
        prev = confirmed[-1]

        # Panic applies immediately
        if raw == Regime.PANIC:
            confirmed.append(Regime.PANIC)
            pending = None
            pending_count = 0
            recover_streak = 0
            continue

        # Recovery from panic → only to bear after N days above MA60
        if prev == Regime.PANIC:
            if both_above_ma[i]:
                recover_streak += 1
            else:
                recover_streak = 0
            if recover_streak >= panic_recover_days:
                confirmed.append(Regime.BEAR)
                pending = None
                pending_count = 0
            else:
                confirmed.append(Regime.PANIC)
            continue

        if raw == prev:
            confirmed.append(prev)
            pending = None
            pending_count = 0
            continue

        if pending == raw:
            pending_count += 1
        else:
            pending = raw
            pending_count = 1

        if pending_count >= confirm_days:
            confirmed.append(raw)
            pending = None
            pending_count = 0
        else:
            confirmed.append(prev)

    return confirmed
