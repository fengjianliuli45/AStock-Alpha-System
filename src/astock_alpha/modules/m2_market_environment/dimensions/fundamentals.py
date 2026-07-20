"""维度5: 经济基本面评分。"""

from __future__ import annotations

from typing import Any


def score_fundamentals(data: dict[str, Any]) -> tuple[float | None, dict[str, Any]]:
    """经济基本面综合评分（0-100）。

    依赖 data:
    - pmi_value: float | None  制造业PMI
    - ppi_value: float | None  PPI同比(%)
    - cpi_value: float | None  CPI同比(%)
    """
    details: dict[str, Any] = {}
    sub_scores: dict[str, float | None] = {}

    # PMI（>50偏多，<49偏空）
    pmi = data.get("pmi_value")
    if pmi is not None:
        if pmi > 50:
            pmi_score = 50.0 + min((pmi - 50) / 5 * 50, 50)
        elif pmi < 49:
            pmi_score = max(0, 40.0 - (49 - pmi) / 5 * 40)
        else:
            pmi_score = 40.0 + (pmi - 49) / 1 * 10
        sub_scores["pmi"] = min(max(pmi_score, 0), 100)
        details["pmi"] = {"value": pmi, "score": sub_scores["pmi"]}
    else:
        sub_scores["pmi"] = None
        details["pmi"] = {"value": None, "note": "missing"}

    # PPI 同比（转正或上行→偏多，<-3%→偏空）
    ppi = data.get("ppi_value")
    if ppi is not None:
        if ppi > 0:
            ppi_score = 55.0 + min(ppi / 5 * 45, 45)
        elif ppi > -3:
            ppi_score = 30.0 + (ppi + 3) / 3 * 25
        else:
            ppi_score = max(0, 30.0 - (abs(ppi) - 3) / 5 * 30)
        sub_scores["ppi"] = min(max(ppi_score, 0), 100)
        details["ppi"] = {"value": ppi, "score": sub_scores["ppi"]}
    else:
        sub_scores["ppi"] = None
        details["ppi"] = {"value": None, "note": "missing"}

    # CPI（1%~2% 温和=最优，>3% 高通胀=偏空）
    cpi = data.get("cpi_value")
    if cpi is not None:
        if 1.0 <= cpi <= 2.0:
            cpi_score = 80.0
        elif 0 <= cpi < 1.0:
            cpi_score = 60.0 + cpi / 1.0 * 20
        elif 2.0 < cpi <= 3.0:
            cpi_score = 60.0 - (cpi - 2.0) / 1.0 * 20
        elif cpi > 3.0:
            cpi_score = max(0, 40.0 - (cpi - 3.0) / 3 * 40)
        else:
            cpi_score = 30.0  # cpi < 0
        sub_scores["cpi"] = min(max(cpi_score, 0), 100)
        details["cpi"] = {"value": cpi, "score": sub_scores["cpi"]}
    else:
        sub_scores["cpi"] = None
        details["cpi"] = {"value": None, "note": "missing"}

    weights = {"pmi": 0.40, "ppi": 0.30, "cpi": 0.30}
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
    details["note"] = "fundamentals"
    return composite, details
