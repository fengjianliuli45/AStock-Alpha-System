from __future__ import annotations

from datetime import date

from astock_alpha.gm_host.orders import apply_target_weights
from astock_alpha.gm_host.runtime import GmHostRuntime
from astock_alpha.modules.m3_universe.snapshots import (
    InMemorySnapshotProvider,
    StockSnapshot,
)
from astock_alpha.modules.registry import build_default_modules
from astock_alpha.pipeline import StrategyPipeline
from astock_alpha.types import PipelineState, Regime


ASOF = date(2024, 6, 3)


def test_apply_target_weights_flattens_old():
    calls: list[tuple[str, float]] = []

    def order(sym: str, pct: float) -> None:
        calls.append((sym, pct))

    apply_target_weights({"A": 0.4, "B": 0.4}, {"A", "C"}, order)
    assert ("C", 0.0) in calls
    assert ("A", 0.4) in calls
    assert ("B", 0.4) in calls


def test_runtime_rebalance_builds_targets():
    snaps = [
        StockSnapshot(
            symbol="SHSE.600000",
            asof=ASOF,
            is_st=False,
            is_delist_risk=False,
            is_suspended=False,
            listed_trading_days=2000,
            avg_amount_20d=5e8,
            total_market_cap=2e11,
            unlock_pct_next_30d=0.0,
            ctrl_shareholder_reduce_60d=False,
            worst_quarter_ni_yoy_180d=0.1,
            goodwill_to_equity=0.05,
            fundamentals_asof=ASOF,
            pledge_ratio=0.1,
            has_fraud_or_violation_5y=False,
            non_standard_audit=False,
            analyst_coverage=5,
        ),
        StockSnapshot(
            symbol="SZSE.000001",
            asof=ASOF,
            is_st=False,
            is_delist_risk=False,
            is_suspended=False,
            listed_trading_days=2000,
            avg_amount_20d=8e8,
            total_market_cap=2e11,
            unlock_pct_next_30d=0.0,
            ctrl_shareholder_reduce_60d=False,
            worst_quarter_ni_yoy_180d=0.1,
            goodwill_to_equity=0.05,
            fundamentals_asof=ASOF,
            pledge_ratio=0.1,
            has_fraud_or_violation_5y=False,
            non_standard_audit=False,
            analyst_coverage=5,
        ),
    ]
    cfg = {
        "strategy_name": "t",
        "version": "v1.0",
        "status": "preregistered",
        "trading_enabled": False,
        "modules": {
            "m0_governance": {"enabled": True, "impl": "builtin"},
            "m1_regime": {"enabled": False},
            "m2_sector": {"enabled": False},
            "m3_universe": {"enabled": True, "impl": "builtin"},
            "m4_fundamentals": {"enabled": False},
            "m5_technical": {"enabled": False},
            "m6_entry": {"enabled": False},
            "m7_sizing": {"enabled": False},
            "m8_exit": {"enabled": False},
            "m9_portfolio_risk": {"enabled": False},
            "m10_monitor": {"enabled": False},
        },
        "governance": {"param_freeze": True},
        "universe": {
            "min_listed_trading_days": 120,
            "min_avg_amount_20d": 1e7,
            "min_total_market_cap": 1e9,
            "max_unlock_pct_next_30d": 0.05,
            "max_goodwill_to_equity": 0.30,
            "max_quarter_ni_yoy_drop": -0.50,
            "max_pledge_ratio": 0.50,
            "min_analyst_coverage": 1,
            "apply_soft_filters": True,
            "enforce_suspension": True,
        },
        "portfolio": {"max_holdings": 2, "cash_floor": 0.0},
        "data": {"provider": None},
    }
    modules = build_default_modules(cfg)
    from astock_alpha.modules.m3_universe import UniverseModule

    modules["m3_universe"] = UniverseModule(
        cfg, provider=InMemorySnapshotProvider(snaps)
    )
    pipe = StrategyPipeline(cfg, modules=modules)
    # Force bull-like multiplier via post-hook: patch by running and overriding
    runtime = GmHostRuntime(cfg, pipeline=pipe)
    orders: list[tuple[str, float]] = []

    def order(sym: str, pct: float) -> None:
        orders.append((sym, pct))

    # Inject regime by wrapping pipeline.run
    orig_run = pipe.run

    def run_with_regime(asof: date) -> PipelineState:
        state = orig_run(asof)
        state.regime = Regime.BULL
        state.regime_multiplier = 1.0
        return state

    pipe.run = run_with_regime  # type: ignore[method-assign]
    state = runtime.run_rebalance(ASOF, current_symbols=[], order_target_percent=order)
    assert state is not None
    assert len(state.targets) == 2
    assert abs(sum(t.weight for t in state.targets) - 1.0) < 1e-9
    assert len(orders) == 2
