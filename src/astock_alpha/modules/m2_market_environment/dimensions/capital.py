"""维度2: 场内资金面评分。"""

from __future__ import annotations

from typing import Any


def score_capital(data: dict[str, Any]) -> tuple[float | None, dict[str, Any]]:
    """场内资金面综合评分（0-100）。

    依赖 data:
    - north_flow_value: float | None  北向资金近20日累计净流入(万元)
    - margin_growth_value: float | None  融资余额近20日增速(%)
    - volume_avg_value: float | None  两市近5日日均成交额(亿元)
    - main_capital_flow_value: float | None  主力资金近5日累计净额(万元)
    """
    details: dict[str, Any] = {}
    sub_scores: dict[str, float | None] = {}

    # 北向资金近20日累计（>300亿偏多，<-200亿偏空）
    nf = data.get("north_flow_value")
    if nf is not None:
        nf_yi = nf / 10000  # 万元→亿元
        if nf_yi > 300:
            nf_score = 60.0 + min((nf_yi - 300) / 200 * 40, 40)
        elif nf_yi < -200:
            nf_score = max(0, 40.0 - (abs(nf_yi) - 200) / 300 * 40)
        else:
            nf_score = 40.0 + (nf_yi + 200) / 500 * 20
        sub_scores["north_flow"] = min(max(nf_score, 0), 100)
        details["north_flow"] = {"value_yi": nf_yi, "score": sub_scores["north_flow"]}
    else:
        sub_scores["north_flow"] = None
        details["north_flow"] = {"value": None, "note": "missing"}

    # 融资余额近20日增速（>3%偏多，<-2%偏空）
    mg = data.get("margin_growth_value")
    if mg is not None:
        if mg > 3:
            mg_score = 60.0 + min((mg - 3) / 3 * 40, 40)
        elif mg < -2:
            mg_score = max(0, 40.0 - (abs(mg) - 2) / 5 * 40)
        else:
            mg_score = 40.0 + (mg + 2) / 5 * 20
        sub_scores["margin_growth"] = min(max(mg_score, 0), 100)
        details["margin_growth"] = {"value_pct": mg, "score": sub_scores["margin_growth"]}
    else:
        sub_scores["margin_growth"] = None
        details["margin_growth"] = {"value": None, "note": "missing"}

    # 两市近5日日均成交额（>1万亿偏多，<6000亿偏空）
    vol = data.get("volume_avg_value")
    if vol is not None:
        if vol > 10000:
            vol_score = 60.0 + min((vol - 10000) / 5000 * 40, 40)
        elif vol < 6000:
            vol_score = max(0, 40.0 - (6000 - vol) / 4000 * 40)
        else:
            vol_score = 40.0 + (vol - 6000) / 4000 * 20
        sub_scores["volume"] = min(max(vol_score, 0), 100)
        details["volume"] = {"value_yi": vol, "score": sub_scores["volume"]}
    else:
        sub_scores["volume"] = None
        details["volume"] = {"value": None, "note": "missing"}

    # 主力资金近5日累计净额（>500亿偏多，<-400亿偏空）
    mcf = data.get("main_capital_flow_value")
    if mcf is not None:
        mcf_yi = mcf / 10000
        if mcf_yi > 500:
            mcf_score = 60.0 + min((mcf_yi - 500) / 300 * 40, 40)
        elif mcf_yi < -400:
            mcf_score = max(0, 40.0 - (abs(mcf_yi) - 400) / 400 * 40)
        else:
            mcf_score = 40.0 + (mcf_yi + 400) / 900 * 20
        sub_scores["main_capital"] = min(max(mcf_score, 0), 100)
        details["main_capital"] = {"value_yi": mcf_yi, "score": sub_scores["main_capital"]}
    else:
        sub_scores["main_capital"] = None
        details["main_capital"] = {"value": None, "note": "missing"}

    weights = {"north_flow": 0.30, "margin_growth": 0.25, "volume": 0.25, "main_capital": 0.20}
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
    details["note"] = "capital"
    return composite, details
