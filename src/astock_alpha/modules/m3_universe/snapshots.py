from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol


@dataclass(slots=True)
class StockSnapshot:
    """Point-in-time attributes known on `asof`. None = unknown (do not invent)."""

    symbol: str
    asof: date
    name: str | None = None
    is_st: bool | None = None
    is_delist_risk: bool | None = None
    is_suspended: bool | None = None
    listed_trading_days: int | None = None
    avg_amount_20d: float | None = None  # CNY
    total_market_cap: float | None = None  # CNY
    buy_blocked_limit_up: bool | None = None  # for m6 entry; not default universe hard reject
    unlock_pct_next_30d: float | None = None  # share of total shares
    ctrl_shareholder_reduce_60d: bool | None = None
    worst_quarter_ni_yoy_180d: float | None = None  # e.g. -0.5
    goodwill_to_equity: float | None = None
    fundamentals_asof: date | None = None  # last known publish/asof for financial fields
    # optional / soft
    pledge_ratio: float | None = None
    has_fraud_or_violation_5y: bool | None = None
    non_standard_audit: bool | None = None
    analyst_coverage: int | None = None


class SnapshotProvider(Protocol):
    def load(self, asof: date, symbols: list[str] | None = None) -> list[StockSnapshot]:
        """Return PIT snapshots for asof. If symbols is None, return full market screen set."""
        ...


class InMemorySnapshotProvider:
    """Test / dry-run provider backed by a preloaded list."""

    def __init__(self, rows: list[StockSnapshot]) -> None:
        self._rows = rows

    def load(self, asof: date, symbols: list[str] | None = None) -> list[StockSnapshot]:
        out = [r for r in self._rows if r.asof == asof]
        if symbols is not None:
            allow = set(symbols)
            out = [r for r in out if r.symbol in allow]
        return out
