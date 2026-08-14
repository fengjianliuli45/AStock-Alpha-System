from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def _daily_rank_ic(factor: pd.Series, y: pd.Series) -> float:
    if factor.nunique(dropna=True) < 3 or y.nunique(dropna=True) < 3:
        return np.nan
    return float(factor.corr(y, method="spearman"))


def rank_ic_stats(df: pd.DataFrame, factor_col: str = "factor") -> dict[str, float]:
    ics: list[float] = []
    for _, g in df.groupby("date", sort=True):
        ic = _daily_rank_ic(g[factor_col], g["y"])
        if np.isfinite(ic):
            ics.append(ic)
    if not ics:
        return {
            "rank_ic_mean": float("nan"),
            "rank_ic_std": float("nan"),
            "rank_ic_ir": float("nan"),
            "n_ic_days": 0,
        }
    arr = np.asarray(ics, dtype=float)
    mean = float(np.mean(arr))
    std = float(np.std(arr, ddof=1)) if len(arr) > 1 else float("nan")
    ir = float(mean / std) if std and np.isfinite(std) and std > 0 else float("nan")
    return {
        "rank_ic_mean": mean,
        "rank_ic_std": std,
        "rank_ic_ir": ir,
        "n_ic_days": int(len(arr)),
    }


def layered_long_short(
    df: pd.DataFrame,
    *,
    factor_col: str = "factor",
    n_quantiles: int = 5,
) -> dict[str, float]:
    ls: list[float] = []
    cover: list[int] = []
    for _, g in df.groupby("date", sort=True):
        g = g.dropna(subset=[factor_col, "y"])
        cover.append(int(len(g)))
        if len(g) < n_quantiles * 3:
            continue
        try:
            q = pd.qcut(g[factor_col], n_quantiles, labels=False, duplicates="drop")
        except ValueError:
            continue
        if q.nunique() < 2:
            continue
        top = int(q.max())
        bot = int(q.min())
        ls.append(float(g.loc[q == top, "y"].mean() - g.loc[q == bot, "y"].mean()))
    if not ls:
        return {
            "ls_mean": float("nan"),
            "ls_std": float("nan"),
            "n_ls_days": 0,
            "avg_names": float(np.mean(cover)) if cover else float("nan"),
        }
    arr = np.asarray(ls, dtype=float)
    return {
        "ls_mean": float(np.mean(arr)),
        "ls_std": float(np.std(arr, ddof=1)) if len(arr) > 1 else float("nan"),
        "n_ls_days": int(len(arr)),
        "avg_names": float(np.mean(cover)) if cover else float("nan"),
    }


def evaluate_split(
    df: pd.DataFrame,
    *,
    n_quantiles: int = 5,
    factor_col: str = "factor",
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    out.update(rank_ic_stats(df, factor_col=factor_col))
    out.update(layered_long_short(df, factor_col=factor_col, n_quantiles=n_quantiles))
    out["n_rows"] = int(len(df))
    out["n_symbols"] = int(df["symbol"].nunique()) if len(df) else 0
    return out
