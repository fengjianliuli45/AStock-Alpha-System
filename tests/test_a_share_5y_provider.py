from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from astock_alpha.data.a_share_5y import AShare5ySnapshotProvider
from astock_alpha.data.providers import build_snapshot_provider
from astock_alpha.modules.m3_universe import UniverseModule
from astock_alpha.types import PipelineState


def _write_mini_panel(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "qfq").mkdir(exist_ok=True)
    dates = pd.bdate_range("2026-01-02", periods=130)
    rows = []
    for i, d in enumerate(dates):
        rows.append(
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
                "amount": 2e8 if i >= 110 else 1e6,  # recent liquid
                "turn": 1.0,
                "pctChg": 0.0,
                "tradestatus": 1,
                "isST": 0,
                "adjustflag": "2",
            }
        )
    # ensure asof 2026-07-02 exists as trading day in range — use last date
    asof = dates[-1].date()
    pd.DataFrame(rows).to_parquet(root / "qfq" / "SHSE.600000.parquet", index=False)

    # ST name on another symbol
    st_rows = []
    for d in dates[-5:]:
        st_rows.append(
            {
                "date": d,
                "symbol": "SZSE.000001",
                "code": "sz.000001",
                "open": 1.0,
                "high": 1.0,
                "low": 1.0,
                "close": 1.0,
                "preclose": 1.0,
                "volume": 1000,
                "amount": 5e8,
                "turn": 1.0,
                "pctChg": 0.0,
                "tradestatus": 1,
                "isST": 1,
                "adjustflag": "2",
            }
        )
    pd.DataFrame(st_rows).to_parquet(root / "qfq" / "SZSE.000001.parquet", index=False)

    inst = pd.DataFrame(
        [
            {
                "code": "sh.600000",
                "code_name": "测试银行",
                "ipoDate": "1999-11-10",
                "outDate": pd.NaT,
                "type": 1,
                "status": 1,
                "symbol": "SHSE.600000",
            },
            {
                "code": "sz.000001",
                "code_name": "*ST测试",
                "ipoDate": "1991-01-01",
                "outDate": pd.NaT,
                "type": 1,
                "status": 1,
                "symbol": "SZSE.000001",
            },
        ]
    )
    inst.to_parquet(root / "instruments.parquet", index=False)
    (root / "ASOF.txt").write_text(asof.isoformat(), encoding="utf-8")


def test_provider_builds_snapshot_and_universe(tmp_path: Path):
    _write_mini_panel(tmp_path)
    asof = date.fromisoformat((tmp_path / "ASOF.txt").read_text(encoding="utf-8").strip())
    provider = AShare5ySnapshotProvider(tmp_path)
    snaps = provider.load(asof)
    assert {s.symbol for s in snaps} == {"SHSE.600000", "SZSE.000001"}
    good = next(s for s in snaps if s.symbol == "SHSE.600000")
    assert good.is_st is False
    assert good.is_suspended is False
    assert good.listed_trading_days == 130
    assert good.avg_amount_20d is not None
    assert good.total_market_cap is None

    mod = UniverseModule(
        config={"universe": {"apply_soft_filters": False}},
        provider=provider,
    )
    assert mod.is_ready()
    state = mod.run(PipelineState(asof=asof))
    assert state.universe == ["SHSE.600000"]
    assert "total_market_cap" in state.incomplete_filters


def test_build_snapshot_provider_from_config(tmp_path: Path):
    _write_mini_panel(tmp_path)
    cfg = {
        "data": {
            "provider": "a_share_5y",
            "a_share_5y_root": str(tmp_path),
            "max_symbols": 1,
        }
    }
    provider = build_snapshot_provider(cfg)
    assert provider is not None
    assert len(provider.list_symbols()) == 1
