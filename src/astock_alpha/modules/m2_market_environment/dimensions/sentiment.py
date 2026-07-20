"""维度4: 市场情绪评分 — 从 m1 的 sentiment 输出读取，不调用外部 API。"""

from __future__ import annotations

from typing import Any


def score_sentiment(m1_sentiment: dict[str, Any] | None) -> tuple[float | None, dict[str, Any]]:
    """市场情绪评分（0-100），从 m1_regime 的 state.meta["sentiment"] 读取。

    依赖:
    - regime: m1 输出的区制（bull/sideways/bear/panic）
    - advance_decline_ratio: 涨跌比
    - limit_up_ratio_zscore: 涨停占比分位秩
    - limit_down_ratio_zscore: 跌停占比分位秩
    - forbid_new_entries / tighten_position / cautious_mode / forbid_chase
    """
    if not m1_sentiment or not isinstance(m1_sentiment, dict):
        return None, {"note": "no m1 sentiment data"}

    details: dict[str, Any] = {}
    sub_scores: dict[str, float | None] = {}

    # 区制（30%）
    regime = (m1_sentiment.get("regime") or "").lower()
    regime_map = {"bull": 80, "sideways": 50, "sideways_lowvol": 45, "sideways_highvol": 35, "bear": 25, "panic": 10}
    regime_score = regime_map.get(regime, 50)
    sub_scores["regime"] = float(regime_score)
    details["regime"] = {"value": regime, "score": regime_score}

    # 涨跌比（20%）— >2:1 偏多，<0.5 偏空
    adr = m1_sentiment.get("advance_decline_ratio")
    if adr is not None:
        try:
            adr_f = float(adr)
            if adr_f >= 2.0:
                adr_score = 60.0 + min((adr_f - 2.0) / 2 * 40, 40)
            elif adr_f <= 0.5:
                adr_score = max(0, 40.0 - (0.5 - adr_f) / 0.5 * 40)
            else:
                adr_score = 40.0 + (adr_f - 0.5) / 1.5 * 20
            sub_scores["advance_decline"] = min(max(adr_score, 0), 100)
            details["advance_decline"] = {"value": adr_f, "score": sub_scores["advance_decline"]}
        except (TypeError, ValueError):
            sub_scores["advance_decline"] = None
            details["advance_decline"] = {"value": None, "note": "parse error"}
    else:
        sub_scores["advance_decline"] = None
        details["advance_decline"] = {"value": None, "note": "missing"}

    # 涨停占比分位（20%）
    up_z = m1_sentiment.get("limit_up_ratio_zscore")
    if up_z is not None:
        try:
            up_f = float(up_z)
            sub_scores["limit_up_z"] = up_f * 100
            details["limit_up_z"] = {"value": up_f, "score": up_f * 100}
        except (TypeError, ValueError):
            sub_scores["limit_up_z"] = None
            details["limit_up_z"] = {"value": None, "note": "parse error"}
    else:
        sub_scores["limit_up_z"] = None
        details["limit_up_z"] = {"value": None, "note": "missing"}

    # 跌停占比分位（20%）— 越低越好，反转
    down_z = m1_sentiment.get("limit_down_ratio_zscore")
    if down_z is not None:
        try:
            down_f = float(down_z)
            sub_scores["limit_down_z"] = (1 - down_f) * 100
            details["limit_down_z"] = {"value": down_f, "score": (1 - down_f) * 100}
        except (TypeError, ValueError):
            sub_scores["limit_down_z"] = None
            details["limit_down_z"] = {"value": None, "note": "parse error"}
    else:
        sub_scores["limit_down_z"] = None
        details["limit_down_z"] = {"value": None, "note": "missing"}

    # 情绪门控信号（10%）— 无触发=高分，多触发=低分
    gates_active = sum(1 for g in ["forbid_new_entries", "tighten_position", "cautious_mode", "forbid_chase"]
                       if m1_sentiment.get(g))
    gate_score = max(0, 100 - gates_active * 25)
    sub_scores["gates"] = float(gate_score)
    details["gates"] = {"active_gates": gates_active, "score": gate_score}

    weights = {"regime": 0.30, "advance_decline": 0.20, "limit_up_z": 0.20, "limit_down_z": 0.20, "gates": 0.10}
    total_w = 0.0
    weighted_sum = 0.0
    for k, w in weights.items():
        s = sub_scores.get(k)
        if s is not None:
            weighted_sum += s * w
            total_w += w
    if total_w == 0:
        return None, {"score": None, "sub_scores": sub_scores, "note": "all sub-dimensions missing"}

    composite = weighted_sum / total_w
    details["composite"] = composite
    details["total_weight"] = total_w
    details["note"] = "sentiment"
    return composite, details
