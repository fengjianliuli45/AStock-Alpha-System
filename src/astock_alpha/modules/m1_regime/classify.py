from __future__ import annotations

import numpy as np
import pandas as pd

from astock_alpha.types import Regime

# Base regimes used by the state machine (vol subtypes applied later in regime.py)
_BASE_REGIMES = frozenset(
    {Regime.BULL, Regime.SIDEWAYS, Regime.BEAR, Regime.PANIC}
)


def ma_slope(ma: pd.Series, lookback: int = 5) -> float | None:
    """MA60斜率 = 当日MA − lookback日前MA。None 表示数据不足。"""
    if len(ma) <= lookback:
        return None
    a = float(ma.iloc[-1])
    b = float(ma.iloc[-1 - lookback])
    if np.isnan(a) or np.isnan(b):
        return None
    return a - b


def _ma_slope_up(ma: pd.Series, lookback: int) -> bool:
    slope = ma_slope(ma, lookback)
    return slope is not None and slope > 0


def _ma_slope_down(ma: pd.Series, lookback: int) -> bool:
    slope = ma_slope(ma, lookback)
    return slope is not None and slope < 0


def classify_index_raw(
    closes: pd.Series,
    *,
    ma_window: int = 60,
    sideways_band: float = 0.03,
    slope_lookback: int = 5,
    panic_day_drop: float = 0.05,
    panic_5d_drop: float = 0.10,
) -> Regime:
    """Classify one index series ending at the last bar (asof).

    MA斜率: 当日MA − 5日前MA；>0 向上，<0 向下，=0 归 SIDEWAYS。
    距MA60 刚好 ±sideways_band（默认 ±3%）→ SIDEWAYS（保守原则，含边界）。
    """
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
    # 含边界：|dist| <= band → SIDEWAYS（刚好 ±3% 归震荡）
    if abs(dist) <= sideways_band:
        return Regime.SIDEWAYS

    slope = ma_slope(ma, slope_lookback)
    if slope is None or slope == 0.0:
        return Regime.SIDEWAYS

    if close > ma_now and slope > 0:
        return Regime.BULL
    if close < ma_now and slope < 0:
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


def _as_base(regime: Regime) -> Regime:
    """Collapse vol subtypes to SIDEWAYS for state-machine transitions."""
    if regime in (Regime.SIDEWAYS_LOWVOL, Regime.SIDEWAYS_HIGHVOL):
        return Regime.SIDEWAYS
    return regime if regime in _BASE_REGIMES else Regime.SIDEWAYS


class RegimeStateMachine:
    """区制状态机（不可越级）。

    流转规则:
    - PANIC → BEAR：恢复需连续 panic_recover_days 天同时站上 MA60
    - BEAR → BULL：必须先连续 confirm_days 天 SIDEWAYS，再连续 confirm_days 天 BULL
    - BULL → BEAR：连续 confirm_days 天 BEAR 直接切换（无需途径 SIDEWAYS）
    - 任何状态维持最少 min_hold_days 个交易日后才允许再次切换
      （PANIC 入场为风控例外，可立即切入）
    """

    def __init__(
        self,
        *,
        confirm_days: int = 2,
        panic_recover_days: int = 3,
        min_hold_days: int = 2,
    ) -> None:
        self.confirm_days = confirm_days
        self.panic_recover_days = panic_recover_days
        self.min_hold_days = min_hold_days

    def walk(
        self,
        combined_raw: list[Regime],
        both_above_ma: list[bool],
    ) -> tuple[list[Regime], list[str]]:
        if not combined_raw:
            return [], []

        confirmed: list[Regime] = [_as_base(combined_raw[0])]
        reasons: list[str] = ["init"]
        pending: Regime | None = None
        pending_count = 0
        recover_streak = 0
        hold_days = 1

        for i in range(1, len(combined_raw)):
            raw = _as_base(combined_raw[i])
            prev = confirmed[-1]
            can_switch = hold_days >= self.min_hold_days

            # PANIC 立即生效（风控例外，不受 min_hold 限制）
            if raw == Regime.PANIC:
                if prev != Regime.PANIC:
                    confirmed.append(Regime.PANIC)
                    reasons.append("panic_immediate")
                    hold_days = 1
                else:
                    confirmed.append(Regime.PANIC)
                    reasons.append("panic_hold")
                    hold_days += 1
                pending = None
                pending_count = 0
                recover_streak = 0
                continue

            # PANIC → BEAR：连续 N 天双指数站上 MA60
            if prev == Regime.PANIC:
                if both_above_ma[i]:
                    recover_streak += 1
                else:
                    recover_streak = 0
                if recover_streak >= self.panic_recover_days and can_switch:
                    confirmed.append(Regime.BEAR)
                    reasons.append(
                        f"panic_recover_to_bear({recover_streak}d_above_ma60)"
                    )
                    pending = None
                    pending_count = 0
                    hold_days = 1
                else:
                    confirmed.append(Regime.PANIC)
                    reasons.append(
                        f"panic_recover_wait({recover_streak}/{self.panic_recover_days})"
                    )
                    hold_days += 1
                continue

            if raw == prev:
                confirmed.append(prev)
                reasons.append("hold_same_raw")
                pending = None
                pending_count = 0
                hold_days += 1
                continue

            # BEAR 不可直接越级到 BULL，必须先经 SIDEWAYS
            if prev == Regime.BEAR and raw == Regime.BULL:
                confirmed.append(prev)
                reasons.append("bear_to_bull_blocked_need_sideways")
                pending = None
                pending_count = 0
                hold_days += 1
                continue

            target = raw
            if pending == target:
                pending_count += 1
            else:
                pending = target
                pending_count = 1

            # min_hold 期间仍累计 pending，但禁止真正切换
            if pending_count >= self.confirm_days and can_switch:
                confirmed.append(target)
                if prev == Regime.BULL and target == Regime.BEAR:
                    reasons.append("bull_to_bear_direct")
                elif prev == Regime.BEAR and target == Regime.SIDEWAYS:
                    reasons.append("bear_to_sideways_gate")
                elif prev == Regime.SIDEWAYS and target == Regime.BULL:
                    reasons.append("sideways_to_bull_confirm")
                else:
                    reasons.append(f"confirm_{prev.value}_to_{target.value}")
                pending = None
                pending_count = 0
                hold_days = 1
            elif pending_count >= self.confirm_days and not can_switch:
                confirmed.append(prev)
                reasons.append(
                    f"min_hold_block({hold_days}/{self.min_hold_days},"
                    f"pending_{target.value})"
                )
                hold_days += 1
            else:
                confirmed.append(prev)
                reasons.append(
                    f"pending_{target.value}({pending_count}/{self.confirm_days})"
                )
                hold_days += 1

        return confirmed, reasons


def walk_confirmed_regimes(
    combined_raw: list[Regime],
    both_above_ma: list[bool],
    *,
    confirm_days: int = 2,
    panic_recover_days: int = 3,
    min_hold_days: int = 2,
) -> list[Regime]:
    """Apply confirmation / panic-recovery along a timeline (state machine)."""
    confirmed, _ = RegimeStateMachine(
        confirm_days=confirm_days,
        panic_recover_days=panic_recover_days,
        min_hold_days=min_hold_days,
    ).walk(combined_raw, both_above_ma)
    return confirmed
