from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class SentimentGates:
    """Daily sentiment overlays from design §1.2."""

    advance_decline_ratio: float | None = None
    limit_up_count: int | None = None
    limit_down_count: int | None = None
    first_board_open_premium: float | None = None
    max_limit_up_streak: int | None = None
    panic_proxy_share: float | None = None

    forbid_new_entries: bool = False
    forbid_short_strategies: bool = False
    forbid_chase: bool = False
    cautious_mode: bool = False
    tighten_position: bool = False
    notes: list[str] | None = None


def evaluate_sentiment(
    *,
    advance_decline_ratio: float | None = None,
    limit_up_count: int | None = None,
    limit_down_count: int | None = None,
    first_board_open_premium: float | None = None,
    max_limit_up_streak: int | None = None,
    panic_proxy_share: float | None = None,
) -> SentimentGates:
    notes: list[str] = []
    gates = SentimentGates(
        advance_decline_ratio=advance_decline_ratio,
        limit_up_count=limit_up_count,
        limit_down_count=limit_down_count,
        first_board_open_premium=first_board_open_premium,
        max_limit_up_streak=max_limit_up_streak,
        panic_proxy_share=panic_proxy_share,
        notes=notes,
    )

    if advance_decline_ratio is not None and advance_decline_ratio < 0.5:
        gates.forbid_new_entries = True
        notes.append("advance_decline<0.5 forbid new entries")

    if limit_up_count is not None and limit_down_count is not None:
        healthy = limit_up_count > 50 and limit_down_count < 20
        if not healthy:
            gates.tighten_position = True
            notes.append("limit-up/down spread unhealthy → tighten")

    if first_board_open_premium is not None and first_board_open_premium < -0.01:
        gates.forbid_short_strategies = True
        notes.append("first-board open premium < -1% forbid short strategies")

    if max_limit_up_streak is not None and max_limit_up_streak <= 2:
        gates.forbid_chase = True
        notes.append("max limit-up streak <= 2 forbid chase")

    if panic_proxy_share is not None and panic_proxy_share > 0.15:
        gates.cautious_mode = True
        notes.append("panic proxy share > 15% cautious mode")

    return gates
