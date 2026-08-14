from __future__ import annotations

from datetime import date, timedelta

from astock_alpha.modules.m3_universe import UniverseModule
from astock_alpha.modules.m3_universe.filters import (
    UniverseFilterConfig,
    evaluate_stock,
)
from astock_alpha.modules.m3_universe.snapshots import (
    InMemorySnapshotProvider,
    StockSnapshot,
)
from astock_alpha.types import PipelineState

ASOF = date(2026, 7, 18)


def _ok(**kwargs) -> StockSnapshot:
    base = dict(
        symbol="000001.SZ",
        asof=ASOF,
        name="平安银行",
        is_st=False,
        is_delist_risk=False,
        is_suspended=False,
        listed_trading_days=2000,
        avg_amount_20d=5e8,
        total_market_cap=2e11,
        buy_blocked_limit_up=False,
        unlock_pct_next_30d=0.0,
        ctrl_shareholder_reduce_60d=False,
        worst_quarter_ni_yoy_180d=0.1,
        goodwill_to_equity=0.05,
        fundamentals_asof=ASOF,
        pledge_ratio=0.1,
        has_fraud_or_violation_5y=False,
        non_standard_audit=False,
        analyst_coverage=5,
    )
    base.update(kwargs)
    return StockSnapshot(**base)


def test_hard_filters_and_pass():
    rows = [
        _ok(symbol="GOOD.SZ"),
        _ok(symbol="ST.SZ", name="*ST示例", is_st=True),
        _ok(symbol="SMALL.SZ", total_market_cap=1e9),
        _ok(symbol="ILLIQ.SZ", avg_amount_20d=1e6),
        _ok(symbol="NEW.SZ", listed_trading_days=30),
        _ok(symbol="UNLOCK.SZ", unlock_pct_next_30d=0.10),
        _ok(symbol="REDUCE.SZ", ctrl_shareholder_reduce_60d=True),
        _ok(symbol="EARN.SZ", worst_quarter_ni_yoy_180d=-0.6),
        _ok(symbol="GW.SZ", goodwill_to_equity=0.4),
        _ok(symbol="HALT.SZ", is_suspended=True),
    ]
    mod = UniverseModule(provider=InMemorySnapshotProvider(rows))
    state = mod.run(PipelineState(asof=ASOF))
    assert state.universe == ["GOOD.SZ"]
    counts = state.meta["universe_reject_counts"]
    assert counts["st_or_delist_risk"] == 1
    assert counts["total_market_cap"] == 1
    assert counts["avg_amount_20d"] == 1
    assert counts["suspended"] == 1


def test_missing_unlock_does_not_reject():
    row = _ok(symbol="MISS.SZ", unlock_pct_next_30d=None)
    mod = UniverseModule(
        config={"universe": {"apply_soft_filters": False}},
        provider=InMemorySnapshotProvider([row]),
    )
    state = mod.run(PipelineState(asof=ASOF))
    assert state.universe == ["MISS.SZ"]
    assert "unlock_pct_next_30d" in state.incomplete_filters


def test_no_provider_degrades():
    mod = UniverseModule()
    assert mod.is_ready() is False
    state = mod.run(PipelineState(asof=ASOF))
    assert state.universe == []
    assert any("no SnapshotProvider" in w for w in state.warnings)


def test_per_day_st_does_not_rewrite_history():
    """Same symbol: non-ST yesterday, ST today — only today's snapshot is rejected."""
    yesterday = ASOF - timedelta(days=1)
    hist = _ok(symbol="X.SZ", asof=yesterday, is_st=False, name="正常股份")
    today = _ok(symbol="X.SZ", asof=ASOF, is_st=True, name="*ST正常")
    assert evaluate_stock(hist, UniverseFilterConfig(apply_soft_filters=False)).passed
    assert not evaluate_stock(today, UniverseFilterConfig(apply_soft_filters=False)).passed


def test_suspended_missing_incomplete():
    row = _ok(symbol="S.SZ", is_suspended=None)
    d = evaluate_stock(row, UniverseFilterConfig(apply_soft_filters=False))
    assert d.passed
    assert "suspended" in d.incomplete_filters


def test_fundamentals_without_pit_not_rejected():
    row = _ok(
        symbol="F.SZ",
        fundamentals_asof=None,
        worst_quarter_ni_yoy_180d=-0.9,
        goodwill_to_equity=0.9,
    )
    d = evaluate_stock(row, UniverseFilterConfig(apply_soft_filters=False))
    assert d.passed
    assert "fundamentals_asof" in d.incomplete_filters


def test_limit_up_not_in_universe_by_default():
    row = _ok(symbol="L.SZ", buy_blocked_limit_up=True)
    d = evaluate_stock(row, UniverseFilterConfig(apply_soft_filters=False))
    assert d.passed
    assert "buy_blocked_limit_up" not in d.reject_reasons


def test_limit_up_in_universe_when_enabled():
    row = _ok(symbol="L.SZ", buy_blocked_limit_up=True)
    cfg = UniverseFilterConfig(apply_soft_filters=False, limit_up_in_universe=True)
    d = evaluate_stock(row, cfg)
    assert not d.passed
    assert "buy_blocked_limit_up" in d.reject_reasons


def test_boundary_listed_days_and_cap():
    cfg = UniverseFilterConfig(apply_soft_filters=False)
    assert evaluate_stock(_ok(listed_trading_days=120), cfg).passed
    assert not evaluate_stock(_ok(listed_trading_days=119), cfg).passed
    assert evaluate_stock(_ok(total_market_cap=5e9), cfg).passed
    assert not evaluate_stock(_ok(total_market_cap=5e9 - 1), cfg).passed
