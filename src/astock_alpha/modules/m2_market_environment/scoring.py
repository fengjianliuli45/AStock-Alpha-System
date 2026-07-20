"""综合打分引擎 — 将五个维度的分数合并为最终环境评级。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class EnvironmentScore:
    """大盘环境综合评分结果。"""

    composite_score: float  # 0-100
    rating: str  # BULL_STRONG / BULL_WEAK / BEAR_WEAK / BEAR_STRONG
    dimension_scores: dict[str, float | None] = field(default_factory=dict)
    dimension_details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "composite_score": round(self.composite_score, 1),
            "rating": self.rating,
            "dimension_scores": {k: round(v, 1) if v is not None else None for k, v in self.dimension_scores.items()},
            "dimension_details": self.dimension_details,
        }


_DEFAULT_WEIGHTS: dict[str, float] = {
    "liquidity": 0.25,
    "capital": 0.20,
    "valuation": 0.20,
    "sentiment": 0.20,
    "fundamentals": 0.15,
}


def compute_environment_score(
    dimension_scores: dict[str, float | None],
    weights: dict[str, float] | None = None,
    dimension_details: dict[str, Any] | None = None,
) -> EnvironmentScore:
    """综合打分。None 的维度自动分配剩余权重，不存在的维度忽略。"""
    w = weights or _DEFAULT_WEIGHTS
    details = dimension_details or {}

    total_weight = 0.0
    weighted_sum = 0.0
    for dim, s in dimension_scores.items():
        wgt = w.get(dim, 0.0)
        if s is not None:
            weighted_sum += s * wgt
            total_weight += wgt

    if total_weight == 0:
        composite = 0.0
    else:
        # 缩放：使实际总权重回归 1.0
        composite = weighted_sum / total_weight

    # rating 阈值（边界处理：>=70 强多，>=50 偏多，>=30 偏空，<30 强空）
    if composite >= 70:
        rating = "BULL_STRONG"
    elif composite >= 50:
        rating = "BULL_WEAK"
    elif composite >= 30:
        rating = "BEAR_WEAK"
    else:
        rating = "BEAR_STRONG"

    return EnvironmentScore(
        composite_score=composite,
        rating=rating,
        dimension_scores=dimension_scores,
        dimension_details=details,
    )
