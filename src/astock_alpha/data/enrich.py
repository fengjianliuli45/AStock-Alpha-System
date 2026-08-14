from __future__ import annotations

from dataclasses import replace
from datetime import date

from astock_alpha.data.tushare_client import TushareHttpClient
from astock_alpha.modules.m3_universe.snapshots import SnapshotProvider, StockSnapshot


class MarketCapEnrichingProvider:
    """Wrap a SnapshotProvider and fill total_market_cap from Tushare daily_basic."""

    def __init__(
        self,
        inner: SnapshotProvider,
        client: TushareHttpClient,
        *,
        enabled: bool = True,
    ) -> None:
        self.inner = inner
        self.client = client
        self.enabled = enabled
        self._cache: dict[date, dict[str, float]] = {}

    def list_symbols(self) -> list[str]:
        if hasattr(self.inner, "list_symbols"):
            return list(self.inner.list_symbols())  # type: ignore[attr-defined]
        return []

    def load(self, asof: date, symbols: list[str] | None = None) -> list[StockSnapshot]:
        snaps = self.inner.load(asof, symbols)
        if not self.enabled or not snaps:
            return snaps
        mv_map = self._mv_map(asof)
        enriched: list[StockSnapshot] = []
        for snap in snaps:
            mv = mv_map.get(snap.symbol)
            if mv is None:
                enriched.append(snap)
            else:
                enriched.append(replace(snap, total_market_cap=mv))
        return enriched

    def _mv_map(self, asof: date) -> dict[str, float]:
        if asof not in self._cache:
            self._cache[asof] = self.client.daily_basic_total_mv_map(asof)
        return self._cache[asof]
