"""维度1: 货币流动性评分。"""

from __future__ import annotations

from typing import Any


def _score_percentile(pct: float | None, bullish_low: float, bearish_high: float) -> float | None:
    """将分位 pct (0-100) 映射到 0-100 分。
    - pct >= bullish_low → 偏多
    - pct <= bearish_high → 偏空
    - 线性插值中性区域
    """
    if pct is None:
        return None
    if pct >= bullish_low:
        return 50.0 + (pct - bullish_low) / (100 - bullish_low) * 50.0
    if pct <= bearish_high:
        return max(0, pct / bearish_high * 50.0)
    return 50.0  # 中性


def score_liquidity(data: dict[str, Any]) -> tuple[float | None, dict[str, Any]]:
    """货币流动性综合评分（0-100）。

    依赖 data 中的 key:
    - m1_growth_value: float | None
    - m1_m2_spread_value: float | None
    - dr007_20d_avg_value: float | None
    - social_financing_value: float | None
    - m1_growth_detail, etc.
    """
    details: dict[str, Any] = {}
    sub_scores: dict[str, float | None] = {}

    # M1同比增速（简化：近 5 年分位 >60 → 偏多，<20 → 偏空）
    m1_v = data.get("m1_growth_value")
    if m1_v is not None:
        sub_scores["m1_growth"] = _score_percentile(m1_v, bullish_low=60, bearish_high=20)
        details["m1_growth"] = {"value": m1_v, "score": sub_scores["m1_growth"]}
    else:
        sub_scores["m1_growth"] = None
        details["m1_growth"] = {"value": None, "note": "missing"}

    # M1-M2 剪刀差（正值 → 偏多，负且低于 -5 → 偏空）
    spread = data.get("m1_m2_spread_value")
    if spread is not None:
        if spread > 0:
            spread_score = 60.0 + min(spread / 5 * 40, 40)
        elif spread > -3:
            spread_score = 40.0 + (spread + 3) / 3 * 20
        else:
            spread_score = max(0, 40.0 - (abs(spread) - 3) / 10 * 40)
        sub_scores["m1_m2_spread"] = min(max(spread_score, 0), 100)
        details["m1_m2_spread"] = {"value": spread, "score": sub_scores["m1_m2_spread"]}
    else:
        sub_scores["m1_m2_spread"] = None
        details["m1_m2_spread"] = {"value": None, "note": "missing"}

    # DR007（<1.5% 偏多，>2.5% 偏空）
    dr007 = data.get("dr007_20d_avg_value")
    if dr007 is not None:
        if dr007 < 1.5:
            dr007_score = 60.0 + (1.5 - dr007) / 1.5 * 40
        elif dr007 > 2.5:
            dr007_score = max(0, 50.0 - (dr007 - 2.5) / 3 * 50)
        else:
            dr007_score = 50.0 + (2.0 - dr007) / 0.5 * 10
        sub_scores["dr007"] = min(max(dr007_score, 0), 100)
        details["dr007"] = {"value": dr007, "score": sub_scores["dr007"]}
    else:
        sub_scores["dr007"] = None
        details["dr007"] = {"value": None, "note": "missing"}

    # 社融存量同比（>10% 偏多，<8% 偏空）
    sf = data.get("social_financing_value")
    if sf is not None:
        if sf > 10:
            sf_score = 60.0 + min((sf - 10) / 5 * 40, 40)
        elif sf < 8:
            sf_score = max(0, 40.0 - (8 - sf) / 5 * 40)
        else:
            sf_score = 40.0 + (sf - 8) / 2 * 20
        sub_scores["social_financing"] = min(max(sf_score, 0), 100)
        details["social_financing"] = {"value": sf, "score": sub_scores["social_financing"]}
    else:
        sub_scores["social_financing"] = None
        details["social_financing"] = {"value": None, "note": "missing"}

    # 加权平均（子权重: M1 35%, M1M2 25%, DR007 25%, 社融 15%）
    weights = {"m1_growth": 0.35, "m1_m2_spread": 0.25, "dr007": 0.25, "social_financing": 0.15}
    total_w = 0.0
    weighted_sum = 0.0
    for k, w in weights.items():
        s = sub_scores.get(k)
        if s is not None:
            weighted_sum += s * w
            total_w += w
    if total_w == 0:
        return None, {"score": None, "sub_scores": sub_scores, "note": "all dimensions missing"}

    composite = weighted_sum / total_w
    details["composite"] = composite
    details["total_weight"] = total_w
    details["note"] = "liquidity"
    return composite, details
