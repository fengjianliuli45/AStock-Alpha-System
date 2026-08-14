from __future__ import annotations

from astock_alpha.types import PipelineState, TargetPosition

REASON = "signal:avg_amount_20d_topn"


def build_signal_targets(
    state: PipelineState,
    amount_by_symbol: dict[str, float | None],
    *,
    max_holdings: int,
    cash_floor: float,
) -> list[TargetPosition]:
    """Map universe → equal-weight Top-N by avg_amount_20d; write ``state.targets``.

    Investable weight ``W = (1 - cash_floor) * regime_multiplier``.
    Missing amounts sort after known amounts. Empty universe or W<=0 → empty targets.
    """
    if max_holdings <= 0:
        state.targets = []
        return state.targets

    cash_floor = min(max(cash_floor, 0.0), 1.0)
    investable = (1.0 - cash_floor) * float(state.regime_multiplier)
    if investable <= 0.0 or not state.universe:
        state.targets = []
        return state.targets

    def sort_key(symbol: str) -> tuple[int, float, str]:
        amt = amount_by_symbol.get(symbol)
        if amt is None:
            return (1, 0.0, symbol)
        return (0, -float(amt), symbol)

    ranked = sorted(state.universe, key=sort_key)
    picked = ranked[:max_holdings]
    k = len(picked)
    if k == 0:
        state.targets = []
        return state.targets

    w = investable / k
    state.targets = [
        TargetPosition(symbol=sym, weight=w, reason=REASON) for sym in picked
    ]
    return state.targets
