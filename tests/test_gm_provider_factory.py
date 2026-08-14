from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd
import pytest

from astock_alpha.data.gm_benchmarks import GmBenchmarkStore
from astock_alpha.data.gm_provider import GmSnapshotProvider
from astock_alpha.data.providers import build_snapshot_provider


ASOF = date(2024, 6, 3)


def test_build_snapshot_provider_gm():
    cfg = {"data": {"provider": "gm", "enrich_market_cap": False, "max_symbols": 10}}
    provider = build_snapshot_provider(cfg)
    assert isinstance(provider, GmSnapshotProvider)
    assert provider.max_symbols == 10


def test_build_snapshot_provider_unknown():
    with pytest.raises(ValueError, match="unknown data.provider"):
        build_snapshot_provider({"data": {"provider": "nope"}})


def test_gm_snapshot_provider_with_injected_api():
    symbols_df = pd.DataFrame(
        [
            {
                "symbol": "SHSE.600000",
                "sec_name": "浦发银行",
                "is_st": False,
                "is_suspended": False,
                "listed_date": datetime(1999, 11, 10),
                "delisted_date": datetime(2038, 1, 1),
            },
            {
                "symbol": "SZSE.000001",
                "sec_name": "平安银行",
                "is_st": False,
                "is_suspended": True,
                "listed_date": datetime(1991, 4, 3),
                "delisted_date": datetime(2038, 1, 1),
            },
        ]
    )

    def get_symbols(**kwargs):
        assert kwargs.get("skip_st") is False
        assert kwargs.get("trade_date") == ASOF.isoformat()
        return symbols_df

    hist_rows = []
    for i in range(25):
        d = ASOF - timedelta(days=40 - i)
        hist_rows.append(
            {"symbol": "SHSE.600000", "eob": d, "amount": 1e8 + i}
        )
        hist_rows.append(
            {"symbol": "SZSE.000001", "eob": d, "amount": 2e8 + i}
        )
    hist_df = pd.DataFrame(hist_rows)

    def history(**kwargs):
        assert "amount" in kwargs.get("fields", "")
        return hist_df

    provider = GmSnapshotProvider(
        amount_window=20,
        get_symbols_fn=get_symbols,
        history_fn=history,
    )
    snaps = provider.load(ASOF)
    assert {s.symbol for s in snaps} == {"SHSE.600000", "SZSE.000001"}
    by_sym = {s.symbol: s for s in snaps}
    assert by_sym["SZSE.000001"].is_suspended is True
    assert by_sym["SHSE.600000"].avg_amount_20d is not None
    assert by_sym["SHSE.600000"].listed_trading_days is not None


def test_gm_benchmark_store_injected():
    def history(**kwargs):
        symbol = kwargs["symbol"]
        rows = []
        for i in range(80):
            d = ASOF - timedelta(days=100 - i)
            rows.append({"eob": d, "close": 1000.0 + i, "symbol": symbol})
        return pd.DataFrame(rows)

    store = GmBenchmarkStore(history_fn=history)
    assert store.exists()
    hs, csi = store.closes_pair(ASOF)
    assert len(hs) > 0
    assert len(csi) > 0
    assert hs.index.max() <= ASOF
