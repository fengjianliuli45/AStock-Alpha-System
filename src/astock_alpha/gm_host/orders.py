from __future__ import annotations

from typing import Protocol


class OrderTargetFn(Protocol):
    def __call__(self, symbol: str, percent: float) -> None: ...


def apply_target_weights(
    target_weights: dict[str, float],
    current_symbols: list[str] | set[str],
    order_target_percent: OrderTargetFn,
) -> list[tuple[str, float]]:
    """Rebalance to target weights; flatten names not in target to 0.

    Returns the list of (symbol, percent) calls made (for tests/logging).
    """
    calls: list[tuple[str, float]] = []
    wanted = set(target_weights)
    for sym in set(current_symbols) - wanted:
        order_target_percent(sym, 0.0)
        calls.append((sym, 0.0))
    for sym, weight in target_weights.items():
        pct = float(weight)
        order_target_percent(sym, pct)
        calls.append((sym, pct))
    return calls
