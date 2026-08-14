from __future__ import annotations

from pathlib import Path
from typing import Any

from astock_alpha.data.a_share_5y import AShare5ySnapshotProvider
from astock_alpha.data.enrich import MarketCapEnrichingProvider
from astock_alpha.data.tushare_client import DEFAULT_HTTP_URL, TushareHttpClient
from astock_alpha.modules.m3_universe.snapshots import SnapshotProvider


def _maybe_enrich_market_cap(
    base: SnapshotProvider, data: dict[str, Any]
) -> SnapshotProvider:
    if not data.get("enrich_market_cap", True):
        return base
    try:
        client = TushareHttpClient(
            http_url=str(data.get("tushare_http_url") or DEFAULT_HTTP_URL),
            token_path=data.get("tushare_token_path"),
        )
        return MarketCapEnrichingProvider(base, client, enabled=True)
    except (FileNotFoundError, ValueError):
        return base


def build_snapshot_provider(config: dict[str, Any]) -> SnapshotProvider | None:
    """Create SnapshotProvider from strategy config `data` section, if configured."""
    data = config.get("data") or {}
    provider = data.get("provider")
    if not provider:
        return None
    if provider == "a_share_5y":
        root = data.get("a_share_5y_root")
        if not root:
            return None
        path = Path(root)
        if not path.exists():
            return None
        max_symbols = data.get("max_symbols")
        base: SnapshotProvider = AShare5ySnapshotProvider(
            path,
            amount_window=int(data.get("amount_window", 20)),
            max_symbols=int(max_symbols) if max_symbols is not None else None,
        )
        return _maybe_enrich_market_cap(base, data)
    if provider == "gm":
        from astock_alpha.data.gm_provider import GmSnapshotProvider

        max_symbols = data.get("max_symbols")
        base = GmSnapshotProvider(
            amount_window=int(data.get("amount_window", 20)),
            max_symbols=int(max_symbols) if max_symbols is not None else None,
            adjust=str(data.get("gm_adjust", "prev")),
            token_path=data.get("gm_token_path"),
        )
        return _maybe_enrich_market_cap(base, data)
    raise ValueError(f"unknown data.provider: {provider}")
