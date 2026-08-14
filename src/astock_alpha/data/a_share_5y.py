from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pandas as pd

from astock_alpha.modules.m3_universe.snapshots import StockSnapshot


def _to_date(value: object) -> date | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    ts = pd.Timestamp(value)
    if pd.isna(ts):
        return None
    return ts.date()


class AShare5ySnapshotProvider:
    """Build PIT StockSnapshots from local BaoStock daily qfq panel (`a_share_5y`).

    Available hard-filter fields: is_st, is_suspended, listed_trading_days, avg_amount_20d, name.
    Not in this dataset (left None → incomplete): market cap, unlock, reduce, fundamentals, etc.
    """

    def __init__(
        self,
        root: str | Path,
        *,
        amount_window: int = 20,
        max_symbols: int | None = None,
    ) -> None:
        self.root = Path(root)
        self.qfq_dir = self.root / "qfq"
        self.amount_window = amount_window
        self.max_symbols = max_symbols
        self._instruments: pd.DataFrame | None = None
        self._df_cache: dict[str, pd.DataFrame] = {}

    def _load_instruments(self) -> pd.DataFrame:
        if self._instruments is None:
            path = self.root / "instruments.parquet"
            if not path.exists():
                raise FileNotFoundError(f"missing instruments.parquet under {self.root}")
            df = pd.read_parquet(path)
            if "symbol" not in df.columns:
                raise ValueError("instruments.parquet must contain symbol column")
            self._instruments = df.set_index("symbol", drop=False)
        return self._instruments

    def list_symbols(self) -> list[str]:
        files = sorted(self.qfq_dir.glob("*.parquet"))
        symbols = [p.stem for p in files]
        if self.max_symbols is not None:
            symbols = symbols[: self.max_symbols]
        return symbols

    def load(self, asof: date, symbols: list[str] | None = None) -> list[StockSnapshot]:
        inst = self._load_instruments()
        wanted = symbols if symbols is not None else self.list_symbols()
        out: list[StockSnapshot] = []
        for symbol in wanted:
            path = self.qfq_dir / f"{symbol}.parquet"
            if not path.exists():
                continue
            snap = self._snapshot_one(path, symbol, asof, inst)
            if snap is not None:
                out.append(snap)
        return out

    def _frame(self, path: Path, symbol: str) -> pd.DataFrame | None:
        cached = self._df_cache.get(symbol)
        if cached is not None:
            return cached
        if not path.exists():
            return None
        df = pd.read_parquet(path)
        if df.empty or "date" not in df.columns:
            return None
        out = df.copy()
        out["date"] = pd.to_datetime(out["date"]).dt.date
        out = out.sort_values("date")
        self._df_cache[symbol] = out
        return out

    def close_on(self, symbol: str, asof: date) -> float | None:
        """Return adjusted close on asof if a bar exists."""
        path = self.qfq_dir / f"{symbol}.parquet"
        df = self._frame(path, symbol)
        if df is None:
            return None
        day = df[df["date"] == asof]
        if day.empty:
            return None
        return float(day.iloc[-1]["close"])

    def _snapshot_one(
        self,
        path: Path,
        symbol: str,
        asof: date,
        inst: pd.DataFrame,
    ) -> StockSnapshot | None:
        df = self._frame(path, symbol)
        if df is None:
            return None
        hist = df[df["date"] <= asof]
        if hist.empty:
            return None
        # require a bar on asof (otherwise not in today's screen)
        day = hist[hist["date"] == asof]
        if day.empty:
            return None
        row = day.iloc[-1]

        amounts = hist["amount"].tail(self.amount_window)
        avg_amount = float(amounts.mean()) if len(amounts) else None

        listed_days = int(len(hist))
        is_st = bool(int(row["isST"])) if "isST" in row.index and pd.notna(row["isST"]) else None
        tradestatus = int(row["tradestatus"]) if "tradestatus" in row.index and pd.notna(
            row["tradestatus"]
        ) else None
        is_suspended = None if tradestatus is None else (tradestatus != 1)

        name = None
        is_delist_risk = None
        if symbol in inst.index:
            meta = inst.loc[symbol]
            if isinstance(meta, pd.DataFrame):
                meta = meta.iloc[0]
            name = None if pd.isna(meta.get("code_name")) else str(meta.get("code_name"))
            out_date = _to_date(meta.get("outDate"))
            if out_date is not None and out_date <= asof:
                is_delist_risk = True
            else:
                is_delist_risk = False

        return StockSnapshot(
            symbol=symbol,
            asof=asof,
            name=name,
            is_st=is_st,
            is_delist_risk=is_delist_risk,
            is_suspended=is_suspended,
            listed_trading_days=listed_days,
            avg_amount_20d=avg_amount,
            total_market_cap=None,  # not in daily panel
            buy_blocked_limit_up=None,
            unlock_pct_next_30d=None,
            ctrl_shareholder_reduce_60d=None,
            worst_quarter_ni_yoy_180d=None,
            goodwill_to_equity=None,
            fundamentals_asof=None,
        )
