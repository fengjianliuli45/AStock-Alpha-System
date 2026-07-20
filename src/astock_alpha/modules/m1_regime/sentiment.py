from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Sequence


@dataclass(slots=True)
class LimitBoardRecord:
    """单只涨跌停明细，供清洗规则使用。"""

    symbol: str
    is_limit_up: bool = False
    is_limit_down: bool = False
    is_st: bool = False
    list_days: int | None = None  # 上市天数；None 视为未知（不按新股剔除）
    is_one_word_limit: bool = False  # 一字无量板


@dataclass(slots=True)
class SentimentGates:
    """Daily sentiment overlays from design §1.2（占比化增强版）。"""

    advance_decline_ratio: float | None = None
    limit_up_count: int | None = None
    limit_down_count: int | None = None
    first_board_open_premium: float | None = None
    max_limit_up_streak: int | None = None
    panic_proxy_share: float | None = None

    # 占比化指标
    limit_up_ratio: float | None = None
    limit_down_ratio: float | None = None
    limit_up_ratio_zscore: float | None = None  # 252 日滚动分位秩 [0,1]
    limit_down_ratio_zscore: float | None = None
    cleaned_limit_up_count: int | None = None
    cleaned_limit_down_count: int | None = None
    total_tradable_symbols: int | None = None

    forbid_new_entries: bool = False
    forbid_short_strategies: bool = False
    forbid_chase: bool = False
    cautious_mode: bool = False
    tighten_position: bool = False
    notes: list[str] | None = None
    meta: dict[str, Any] = field(default_factory=dict)


def clean_limit_boards(
    boards: Sequence[LimitBoardRecord],
    *,
    min_list_days: int = 10,
) -> tuple[list[LimitBoardRecord], dict[str, int]]:
    """清洗规则：剔除 ST、上市未满 min_list_days 新股、一字无量板。"""
    kept: list[LimitBoardRecord] = []
    stats = {
        "input": len(boards),
        "dropped_st": 0,
        "dropped_new_list": 0,
        "dropped_one_word": 0,
        "kept": 0,
    }
    for b in boards:
        if b.is_st:
            stats["dropped_st"] += 1
            continue
        if b.list_days is not None and b.list_days < min_list_days:
            stats["dropped_new_list"] += 1
            continue
        if b.is_one_word_limit:
            stats["dropped_one_word"] += 1
            continue
        kept.append(b)
    stats["kept"] = len(kept)
    return kept, stats


def _percentile_rank(history: Sequence[float], value: float) -> float:
    """当前值在样本中的分位秩（含自身），范围 [0, 1]。"""
    if not history:
        return 0.5
    n = len(history)
    below = sum(1 for x in history if x < value)
    equal = sum(1 for x in history if x == value)
    return (below + 0.5 * equal) / n


class SentimentRollingWindow:
    """涨跌停占比的 252 日滚动窗口，用于分位数门控。"""

    def __init__(self, window: int = 252) -> None:
        self.window = window
        self._up: deque[float] = deque(maxlen=window)
        self._down: deque[float] = deque(maxlen=window)

    def update(
        self, up_ratio: float, down_ratio: float
    ) -> tuple[float, float]:
        self._up.append(float(up_ratio))
        self._down.append(float(down_ratio))
        return (
            _percentile_rank(self._up, float(up_ratio)),
            _percentile_rank(self._down, float(down_ratio)),
        )

    @property
    def size(self) -> int:
        return len(self._up)


def evaluate_sentiment(
    *,
    advance_decline_ratio: float | None = None,
    limit_up_count: int | None = None,
    limit_down_count: int | None = None,
    first_board_open_premium: float | None = None,
    max_limit_up_streak: int | None = None,
    panic_proxy_share: float | None = None,
    total_tradable_symbols: int | None = None,
    limit_boards: Sequence[LimitBoardRecord] | None = None,
    rolling_window: SentimentRollingWindow | None = None,
    min_list_days: int = 10,
    up_ratio_tighten_quantile: float = 0.20,
    down_ratio_cautious_quantile: float = 0.80,
    min_history_for_quantile: int = 20,
) -> SentimentGates:
    notes: list[str] = []
    clean_stats: dict[str, int] = {}
    cleaned_up: int | None = limit_up_count
    cleaned_down: int | None = limit_down_count

    if limit_boards is not None:
        kept, clean_stats = clean_limit_boards(
            limit_boards, min_list_days=min_list_days
        )
        cleaned_up = sum(1 for b in kept if b.is_limit_up)
        cleaned_down = sum(1 for b in kept if b.is_limit_down)
        notes.append(
            "limit_boards_cleaned:"
            f"st={clean_stats.get('dropped_st', 0)},"
            f"new={clean_stats.get('dropped_new_list', 0)},"
            f"one_word={clean_stats.get('dropped_one_word', 0)}"
        )

    up_ratio: float | None = None
    down_ratio: float | None = None
    up_pct: float | None = None
    down_pct: float | None = None

    if (
        total_tradable_symbols is not None
        and total_tradable_symbols > 0
        and cleaned_up is not None
        and cleaned_down is not None
    ):
        up_ratio = cleaned_up / total_tradable_symbols
        down_ratio = cleaned_down / total_tradable_symbols
        if rolling_window is not None:
            up_pct, down_pct = rolling_window.update(up_ratio, down_ratio)

    gates = SentimentGates(
        advance_decline_ratio=advance_decline_ratio,
        limit_up_count=limit_up_count,
        limit_down_count=limit_down_count,
        first_board_open_premium=first_board_open_premium,
        max_limit_up_streak=max_limit_up_streak,
        panic_proxy_share=panic_proxy_share,
        limit_up_ratio=up_ratio,
        limit_down_ratio=down_ratio,
        limit_up_ratio_zscore=up_pct,
        limit_down_ratio_zscore=down_pct,
        cleaned_limit_up_count=cleaned_up,
        cleaned_limit_down_count=cleaned_down,
        total_tradable_symbols=total_tradable_symbols,
        notes=notes,
        meta={"clean_stats": clean_stats} if clean_stats else {},
    )

    if advance_decline_ratio is not None and advance_decline_ratio < 0.5:
        gates.forbid_new_entries = True
        notes.append("advance_decline<0.5 forbid new entries")

    # 占比 + 滚动分位数门控（优先）
    quantile_applied = False
    hist_n = rolling_window.size if rolling_window is not None else 0
    if (
        up_pct is not None
        and down_pct is not None
        and hist_n >= min_history_for_quantile
    ):
        quantile_applied = True
        if up_pct < up_ratio_tighten_quantile:
            gates.tighten_position = True
            notes.append(
                f"limit_up_ratio pctile={up_pct:.3f}<{up_ratio_tighten_quantile} → tighten"
            )
        if down_pct > down_ratio_cautious_quantile:
            gates.cautious_mode = True
            notes.append(
                f"limit_down_ratio pctile={down_pct:.3f}>{down_ratio_cautious_quantile} → cautious"
            )

    # 兼容旧绝对家数阈值（无占比分位时回退）
    if (
        not quantile_applied
        and cleaned_up is not None
        and cleaned_down is not None
    ):
        healthy = cleaned_up > 50 and cleaned_down < 20
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
