from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def load_symbol_frame(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path)
    need = {"date", "close"}
    missing = need - set(df.columns)
    if missing:
        raise ValueError(f"{path.name} missing columns: {sorted(missing)}")
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    if "symbol" not in df.columns:
        df["symbol"] = path.stem
    for col in ("open", "high", "low", "close", "volume", "amount", "turn"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.sort_values("date").reset_index(drop=True)


def load_panel(
    data_root: Path,
    symbols: list[str],
    *,
    years: float = 2.0,
    max_symbols: int | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    qfq = data_root / "qfq"
    if not qfq.is_dir():
        raise FileNotFoundError(f"qfq directory not found: {qfq}")

    use = list(symbols)
    if max_symbols is not None:
        use = use[: max_symbols]

    frames: list[pd.DataFrame] = []
    missing: list[str] = []
    for sym in use:
        path = qfq / f"{sym}.parquet"
        if not path.exists():
            missing.append(sym)
            continue
        frames.append(load_symbol_frame(path))

    if not frames:
        raise RuntimeError("no constituent parquet files found under qfq")

    panel = pd.concat(frames, ignore_index=True)
    end = panel["date"].max()
    start = end - pd.Timedelta(days=int(round(years * 365.25)))
    # warm-up buffer for 20d features
    load_start = start - pd.Timedelta(days=60)
    panel = panel[(panel["date"] >= load_start) & (panel["date"] <= end)].copy()
    panel = panel.sort_values(["symbol", "date"]).reset_index(drop=True)

    summary = {
        "data_root": str(data_root),
        "n_requested": len(use),
        "n_loaded": int(panel["symbol"].nunique()),
        "n_missing_files": len(missing),
        "missing_sample": missing[:20],
        "date_min_raw": str(panel["date"].min().date()),
        "date_max": str(end.date()),
        "window_start": str(start.date()),
        "years": years,
        "rows_raw": int(len(panel)),
    }
    return panel, summary


def time_split_dates(
    dates: pd.Series,
    *,
    train_frac: float,
    purge_days: int,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    uniq = np.array(sorted(pd.to_datetime(dates).unique()))
    if len(uniq) < 40:
        raise ValueError(f"too few trading days for split: {len(uniq)}")
    cut = int(len(uniq) * train_frac)
    cut = max(20, min(cut, len(uniq) - 10))
    train_end_idx = cut - 1
    oos_start_idx = cut + max(0, purge_days)
    if oos_start_idx >= len(uniq):
        raise ValueError("purge removed all OOS dates; reduce purge or years")
    train_dates = uniq[: train_end_idx + 1]
    oos_dates = uniq[oos_start_idx:]
    meta = {
        "n_dates": int(len(uniq)),
        "n_train_dates": int(len(train_dates)),
        "n_oos_dates": int(len(oos_dates)),
        "train_start": str(pd.Timestamp(train_dates[0]).date()),
        "train_end": str(pd.Timestamp(train_dates[-1]).date()),
        "oos_start": str(pd.Timestamp(oos_dates[0]).date()),
        "oos_end": str(pd.Timestamp(oos_dates[-1]).date()),
        "purge_days": int(purge_days),
    }
    return train_dates, oos_dates, meta
