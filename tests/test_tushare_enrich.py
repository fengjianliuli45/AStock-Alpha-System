from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from astock_alpha.data.a_share_5y import AShare5ySnapshotProvider
from astock_alpha.data.enrich import MarketCapEnrichingProvider
from astock_alpha.data.tushare_client import gm_to_ts_code, ts_to_gm_symbol
from astock_alpha.modules.m3_universe import UniverseModule
from astock_alpha.types import PipelineState

ASOF = date(2026, 7, 2)


def test_symbol_roundtrip():
    assert gm_to_ts_code("SHSE.600000") == "600000.SH"
    assert gm_to_ts_code("SZSE.000001") == "000001.SZ"
    assert ts_to_gm_symbol("600000.SH") == "SHSE.600000"


class _FakeClient:
    def daily_basic_total_mv_map(self, trade_date: date) -> dict[str, float]:
        assert trade_date == ASOF
        return {"SHSE.600000": 8e10}  # 800 亿


def test_enrich_market_cap_filters(tmp_path: Path):
    dates = pd.bdate_range(end=ASOF, periods=130)
    (tmp_path / "qfq").mkdir()
    rows = [
        {
            "date": d,
            "symbol": "SHSE.600000",
            "code": "sh.600000",
            "open": 10.0,
            "high": 10.0,
            "low": 10.0,
            "close": 10.0,
            "preclose": 10.0,
            "volume": 1_000_000,
            "amount": 2e8,
            "turn": 1.0,
            "pctChg": 0.0,
            "tradestatus": 1,
            "isST": 0,
            "adjustflag": "2",
        }
        for d in dates
    ]
    pd.DataFrame(rows).to_parquet(tmp_path / "qfq" / "SHSE.600000.parquet", index=False)
    pd.DataFrame(
        [
            {
                "code": "sh.600000",
                "code_name": "测试银行",
                "ipoDate": "1999-11-10",
                "outDate": pd.NaT,
                "type": 1,
                "status": 1,
                "symbol": "SHSE.600000",
            }
        ]
    ).to_parquet(tmp_path / "instruments.parquet", index=False)

    inner = AShare5ySnapshotProvider(tmp_path)
    provider = MarketCapEnrichingProvider(inner, _FakeClient())  # type: ignore[arg-type]
    snaps = provider.load(ASOF)
    assert snaps[0].total_market_cap == 8e10

    mod = UniverseModule(
        config={"universe": {"apply_soft_filters": False}},
        provider=provider,
    )
    state = mod.run(PipelineState(asof=ASOF))
    assert state.universe == ["SHSE.600000"]
    assert "total_market_cap" not in state.incomplete_filters
