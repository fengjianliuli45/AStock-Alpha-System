from __future__ import annotations

from datetime import date

from astock_alpha.portfolio.signal_adapter import REASON, build_signal_targets
from astock_alpha.types import PipelineState, Regime


ASOF = date(2026, 8, 5)


def _state(universe: list[str], mult: float = 1.0) -> PipelineState:
    return PipelineState(
        asof=ASOF,
        regime=Regime.BULL if mult >= 1.0 else Regime.SIDEWAYS,
        regime_multiplier=mult,
        universe=list(universe),
    )


def test_top_n_by_amount_equal_weight():
    state = _state(["A", "B", "C", "D"], mult=1.0)
    amounts = {"A": 1e8, "B": 3e8, "C": 2e8, "D": 4e8}
    targets = build_signal_targets(
        state, amounts, max_holdings=2, cash_floor=0.0
    )
    assert [t.symbol for t in targets] == ["D", "B"]
    assert all(abs(t.weight - 0.5) < 1e-9 for t in targets)
    assert all(t.reason == REASON for t in targets)
    assert state.targets is targets


def test_cash_floor_and_regime_multiplier():
    state = _state(["A", "B"], mult=0.5)
    amounts = {"A": 2e8, "B": 1e8}
    targets = build_signal_targets(
        state, amounts, max_holdings=2, cash_floor=0.2
    )
    # W = (1-0.2)*0.5 = 0.4 → 0.2 each
    assert len(targets) == 2
    assert abs(targets[0].weight - 0.2) < 1e-9
    assert abs(sum(t.weight for t in targets) - 0.4) < 1e-9


def test_panic_multiplier_empty():
    state = _state(["A", "B"], mult=0.0)
    targets = build_signal_targets(
        state, {"A": 1e8, "B": 2e8}, max_holdings=2, cash_floor=0.05
    )
    assert targets == []
    assert state.targets == []


def test_missing_amount_sorts_last():
    state = _state(["A", "B", "C"], mult=1.0)
    amounts = {"A": None, "B": 1e8, "C": None}
    targets = build_signal_targets(
        state, amounts, max_holdings=2, cash_floor=0.0
    )
    assert [t.symbol for t in targets] == ["B", "A"]


def test_empty_universe():
    state = _state([], mult=1.0)
    targets = build_signal_targets(state, {}, max_holdings=3, cash_floor=0.05)
    assert targets == []


def test_max_holdings_zero():
    state = _state(["A"], mult=1.0)
    targets = build_signal_targets(
        state, {"A": 1e8}, max_holdings=0, cash_floor=0.0
    )
    assert targets == []
