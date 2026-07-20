from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd


def load_index_closes(path: Path, asof: date) -> pd.Series:
    """Load close series indexed by date, truncated to asof inclusive."""
    df = pd.read_parquet(path)
    if "date" not in df.columns or "close" not in df.columns:
        raise ValueError(f"benchmark file missing date/close: {path}")
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"]).dt.date
    out = out[out["date"] <= asof].sort_values("date")
    return pd.Series(out["close"].astype(float).values, index=pd.Index(out["date"]), name=path.stem)


class BenchmarkStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.hs300_path = self.root / "CSI300.parquet"
        self.csi500_path = self.root / "CSI500.parquet"

    def exists(self) -> bool:
        return self.hs300_path.exists() and self.csi500_path.exists()

    def closes_pair(self, asof: date) -> tuple[pd.Series, pd.Series]:
        return (
            load_index_closes(self.hs300_path, asof),
            load_index_closes(self.csi500_path, asof),
        )
