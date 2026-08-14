from __future__ import annotations

import numpy as np
import pandas as pd

from research.gplearn_mine.config import FEATURE_NAMES


def build_feature_frame(
    panel: pd.DataFrame,
    *,
    horizon: int,
    window_start: pd.Timestamp,
    winsor_pct: float = 0.01,
) -> pd.DataFrame:
    """Build point-in-time features + forward label; cross-sectionally rank features."""
    df = panel.sort_values(["symbol", "date"]).copy()
    g = df.groupby("symbol", group_keys=False)

    df["ret_1"] = g["close"].pct_change(1)
    df["ret_5"] = g["close"].pct_change(5)
    df["ret_20"] = g["close"].pct_change(20)
    df["vol_20"] = g["ret_1"].transform(lambda s: s.rolling(20, min_periods=10).std())
    amt_ma = g["amount"].transform(lambda s: s.rolling(20, min_periods=10).mean())
    df["amt_ma_ratio"] = df["amount"] / amt_ma.replace(0, np.nan)
    if "turn" in df.columns:
        df["turn"] = df["turn"]
    else:
        df["turn"] = df["volume"]
    df["hl_range"] = (df["high"] - df["low"]) / df["close"].replace(0, np.nan)
    ma20 = g["close"].transform(lambda s: s.rolling(20, min_periods=10).mean())
    df["ma_gap_20"] = df["close"] / ma20.replace(0, np.nan) - 1.0
    v_ma = g["volume"].transform(lambda s: s.rolling(20, min_periods=10).mean())
    df["v_ma_ratio"] = df["volume"] / v_ma.replace(0, np.nan)
    high20 = g["high"].transform(lambda s: s.rolling(20, min_periods=10).max())
    df["ret_from_high_20"] = df["close"] / high20.replace(0, np.nan) - 1.0

    fwd = g["close"].shift(-horizon)
    df["y"] = fwd / df["close"] - 1.0

    # drop warm-up outside analysis window and rows without label
    df = df[df["date"] >= pd.Timestamp(window_start)].copy()
    df = df.dropna(subset=["y", "close"]).copy()

    if winsor_pct and winsor_pct > 0:
        lo = df["y"].quantile(winsor_pct)
        hi = df["y"].quantile(1.0 - winsor_pct)
        df["y"] = df["y"].clip(lo, hi)

    # cross-sectional rank of features by date
    idx = df.set_index("date")
    for name in FEATURE_NAMES:
        if name not in idx.columns:
            idx[name] = np.nan
        ranked = idx[name].groupby(level=0).rank(pct=True)
        df[name] = ranked.to_numpy()

    df = df.dropna(subset=FEATURE_NAMES + ["y"]).reset_index(drop=True)
    return df[["date", "symbol", *FEATURE_NAMES, "y"]]
