"""维度3: 全市场估值水位评分。"""

from __future__ import annotations

from typing import Any


def score_valuation(data: dict[str, Any]) -> tuple[float | None, dict[str, Any]]:
    """全市场估值水位综合评分（0-100）。

    依赖 data:
    - pe_percentile_value: float | None  PE-TTM近10年分位(0-100)，越低越安全
    - risk_premium_value: float | None  风险溢价分位(0-100)，越高股票性价比越优
    - lot_break_ratio_value: float | None  破净股占比(%)
    """
    details: dict[str, Any] = {}
    sub_scores: dict[str, float | None] = {}

    # PE分位（<30 → 低估偏多，>70 → 高估偏空）
    pe = data.get("pe_percentile_value")
    if pe is not None:
        if pe < 30:
            pe_score = 60.0 + (30 - pe) / 30 * 40
        elif pe > 70:
            pe_score = max(0, 40.0 - (pe - 70) / 30 * 40)
        else:
            pe_score = 40.0 + (70 - pe) / 40 * 20
        sub_scores["pe"] = min(max(pe_score, 0), 100)
        details["pe"] = {"value_pct": pe, "score": sub_scores["pe"]}
    else:
        sub_scores["pe"] = None
        details["pe"] = {"value": None, "note": "missing"}

    # 风险溢价（分位 >70 → 偏多，<30 → 偏空）
    rp = data.get("risk_premium_value")
    if rp is not None:
        if rp > 70:
            rp_score = 60.0 + min((rp - 70) / 30 * 40, 40)
        elif rp < 30:
            rp_score = max(0, 40.0 - (30 - rp) / 30 * 40)
        else:
            rp_score = 40.0 + (rp - 30) / 40 * 20
        sub_scores["risk_premium"] = min(max(rp_score, 0), 100)
        details["risk_premium"] = {"value_pct": rp, "score": sub_scores["risk_premium"]}
    else:
        sub_scores["risk_premium"] = None
        details["risk_premium"] = {"value": None, "note": "missing"}

    # 破净股占比（>8% 偏多(底部信号)，<1% 偏空(过热)）
    lbr = data.get("lot_break_ratio_value")
    if lbr is not None:
        if lbr > 8:
            lbr_score = 60.0 + min((lbr - 8) / 10 * 40, 40)
        elif lbr < 1:
            lbr_score = max(0, 40.0 - (1 - lbr) / 1 * 40)
        else:
            lbr_score = 40.0 + (lbr - 1) / 7 * 20
        sub_scores["lot_break"] = min(max(lbr_score, 0), 100)
        details["lot_break"] = {"value_pct": lbr, "score": sub_scores["lot_break"]}
    else:
        sub_scores["lot_break"] = None
        details["lot_break"] = {"value": None, "note": "missing"}

    weights = {"pe": 0.35, "risk_premium": 0.35, "lot_break": 0.30}
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
    details["note"] = "valuation"
    return composite, details
