"""Tushare 宏观数据采集器 — 供 m2_market_environment 使用。

每个函数返回 (value: float | None, detail: dict)，失败返回 (None, {"error": str})。
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from astock_alpha.data.tushare_client import (
    TushareHttpClient,
    DEFAULT_HTTP_URL,
)


def _client(token: str | None = None, http_url: str | None = None) -> TushareHttpClient:
    return TushareHttpClient(
        token=token or "",
        http_url=http_url or DEFAULT_HTTP_URL,
    )


def _last_n_trade_days(asof: date, n: int) -> date:
    """粗略往前推 N 个自然日（用于宏观历史）。"""
    return asof - timedelta(days=n * 2)


# ── 维度1: 货币流动性 ─────────────────────────────────────


def fetch_m1_growth(
    token: str | None = None, http_url: str | None = None
) -> tuple[float | None, dict[str, Any]]:
    """M1 同比增速(%)。"""
    cli = _client(token, http_url)
    try:
        rows = cli.query("cn_m", params={"indicator": "M1_同比"})
        if not rows:
            return None, {"error": "no data"}
        val = rows[0].get("value") or rows[0].get("m1_growth")
        if val is None:
            return None, {"error": "field not found"}
        return float(val), {"source": "tushare.cn_m"}
    except Exception as e:
        return None, {"error": str(e)}


def fetch_m1_m2_spread(
    token: str | None = None, http_url: str | None = None
) -> tuple[float | None, dict[str, Any]]:
    """M1-M2 剪刀差（M1同比 - M2同比百分点）。"""
    cli = _client(token, http_url)
    try:
        m1 = cli.query("cn_m", params={"indicator": "M1_同比"})
        m2 = cli.query("cn_m", params={"indicator": "M2_同比"})
        m1v = float(m1[0].get("value")) if m1 and m1[0].get("value") is not None else None
        m2v = float(m2[0].get("value")) if m2 and m2[0].get("value") is not None else None
        if m1v is not None and m2v is not None:
            return m1v - m2v, {"m1": m1v, "m2": m2v}
        return None, {"error": "missing m1 or m2"}
    except Exception as e:
        return None, {"error": str(e)}


def fetch_dr007_20d_avg(
    asof: date,
    token: str | None = None,
    http_url: str | None = None,
) -> tuple[float | None, dict[str, Any]]:
    """DR007 近 20 个交易日均值(折年%)。"""
    cli = _client(token, http_url)
    start = _last_n_trade_days(asof, 25)
    try:
        rows = cli.query("shibor", params={
            "start_date": start.strftime("%Y%m%d"),
            "end_date": asof.strftime("%Y%m%d"),
        })
        vals = []
        for r in rows:
            v = r.get("7") or r.get("7_ior")
            if v is not None:
                try:
                    vals.append(float(v))
                except (TypeError, ValueError):
                    continue
        if not vals:
            return None, {"error": "no valid dr007 rows"}
        avg = sum(vals) / len(vals)
        return avg, {"count": len(vals), "last": vals[-1] if vals else None}
    except Exception as e:
        return None, {"error": str(e)}


def fetch_social_financing(
    token: str | None = None, http_url: str | None = None
) -> tuple[float | None, dict[str, Any]]:
    """社会融资规模存量同比增速(%)。"""
    cli = _client(token, http_url)
    try:
        rows = cli.query("cn_sf", params={"indicator": "社会融资规模存量_同比"})
        if not rows:
            return None, {"error": "no data"}
        val = rows[0].get("value")
        if val is None:
            return None, {"error": "field not found"}
        return float(val), {"source": "tushare.cn_sf"}
    except Exception as e:
        return None, {"error": str(e)}


# ── 维度2: 场内资金面 ──────────────────────────────────────


def fetch_north_bound_flow(
    asof: date | None = None,
    token: str | None = None,
    http_url: str | None = None,
) -> tuple[float | None, dict[str, Any]]:
    """北向资金近 20 日累计净流入(万元)。"""
    cli = _client(token, http_url)
    try:
        rows = cli.query("moneyflow_hsgt", params={"trade_date": ""})
        vals = []
        for r in rows[:100]:
            net = r.get("net_hsgt") or r.get("north_net_flow")
            if net is not None:
                try:
                    vals.append(float(net))
                except (TypeError, ValueError):
                    continue
        recent = vals[-20:] if len(vals) >= 20 else vals
        total = sum(recent)
        return total, {"count": len(recent), "last_net": recent[-1] if recent else None}
    except Exception as e:
        return None, {"error": str(e)}


def fetch_margin_balance_growth(
    asof: date | None = None,
    token: str | None = None,
    http_url: str | None = None,
) -> tuple[float | None, dict[str, Any]]:
    """融资余额近 20 日增速(%)。"""
    cli = _client(token, http_url)
    try:
        rows = cli.query("margin", params={})
        if not rows:
            return None, {"error": "no data"}
        vals = []
        for r in rows[:30]:
            bal = r.get("balance") or r.get("margin_balance")
            if bal is not None:
                try:
                    vals.append(float(bal))
                except (TypeError, ValueError):
                    continue
        if len(vals) < 2:
            return None, {"error": f"insufficient rows ({len(vals)})"}
        recent_20 = vals[-20:] if len(vals) >= 20 else vals
        growth = (recent_20[-1] - recent_20[0]) / recent_20[0] * 100.0
        return growth, {"start": recent_20[0], "end": recent_20[-1], "count": len(recent_20)}
    except Exception as e:
        return None, {"error": str(e)}


def fetch_market_volume_avg(
    asof: date | None = None,
    token: str | None = None,
    http_url: str | None = None,
) -> tuple[float | None, dict[str, Any]]:
    """两市近 5 日日均成交额(亿元)。"""
    cli = _client(token, http_url)
    try:
        rows = cli.query("daily_basic", params={"trade_date": ""})
        if not rows:
            rows = cli.query("index_daily", params={})
        vals = []
        for r in rows[:10]:
            amt = r.get("amount") or r.get("total_amount")
            if amt is not None:
                try:
                    vals.append(float(amt))
                except (TypeError, ValueError):
                    continue
        recent = vals[-5:] if len(vals) >= 5 else vals
        if not recent:
            return None, {"error": "no amount data"}
        avg = sum(recent) / len(recent)
        return avg, {"count": len(recent), "last": recent[-1] if recent else None}
    except Exception as e:
        return None, {"error": str(e)}


def fetch_main_capital_flow(
    asof: date | None = None,
    token: str | None = None,
    http_url: str | None = None,
) -> tuple[float | None, dict[str, Any]]:
    """主力资金（超大单+大单）近 5 日累计净额(万元)。"""
    cli = _client(token, http_url)
    try:
        rows = cli.query("moneyflow", params={})
        vals = []
        for r in rows[:10]:
            net = r.get("net_main")
            if net is not None:
                try:
                    vals.append(float(net))
                except (TypeError, ValueError):
                    continue
        recent = vals[-5:] if len(vals) >= 5 else vals
        total = sum(recent)
        return total, {"count": len(recent), "last": recent[-1] if recent else None}
    except Exception as e:
        return None, {"error": str(e)}


# ── 维度3: 估值水位 ─────────────────────────────────────────


def fetch_market_pe_percentile(
    token: str | None = None, http_url: str | None = None
) -> tuple[float | None, dict[str, Any]]:
    """万得全A PE-TTM 近 10 年分位(0~100)。"""
    cli = _client(token, http_url)
    try:
        rows = cli.query("index_global", params={})
        for r in rows:
            idx = r.get("index_code") or r.get("ts_code") or ""
            if "全A" in idx or "881001" in idx:
                pct = r.get("pe_percentile") or r.get("pe_ttm_percentile")
                if pct is not None:
                    return float(pct), {"index": idx}
                return None, {"error": "pe_percentile not found"}
        return None, {"error": "all_cn index not found"}
    except Exception as e:
        return None, {"error": str(e)}


def fetch_risk_premium(
    token: str | None = None, http_url: str | None = None
) -> tuple[float | None, dict[str, Any]]:
    """风险溢价分位(0~100) — 市盈率倒数 - 10Y国债收益率。

    先用 PE 和国债收益率简单估算，后续可精确化。
    """
    cli = _client(token, http_url)
    try:
        pe_rows = cli.query("index_global", params={})
        pe = None
        for r in pe_rows:
            idx = r.get("index_code") or r.get("ts_code") or ""
            if "全A" in idx or "881001" in idx:
                pe_v = r.get("pe") or r.get("pe_ttm")
                if pe_v is not None:
                    pe = float(pe_v)
                break
        bond_rows = cli.query("shibor", params={"indicator": "10Y"})
        if not bond_rows:
            bond_rows = cli.query("cn_bond", params={"indicator": "国债_10Y"})
        bond_yield = None
        if bond_rows:
            by = bond_rows[0].get("value") or bond_rows[0].get("yield") or bond_rows[0].get("10")
            if by is not None:
                bond_yield = float(by)
        if pe and bond_yield and pe > 0:
            premium = (1.0 / pe - bond_yield / 100.0) * 100.0
            # 简单映射到 0-100 分位（假设合理范围 -2~6）
            pct = min(max((premium + 2.0) / 8.0 * 100.0, 0.0), 100.0)
            return pct, {"premium": premium, "pe": pe, "bond_yield": bond_yield}
        return None, {"error": "missing pe or bond_yield"}
    except Exception as e:
        return None, {"error": str(e)}


def fetch_lot_break_ratio(
    asof: date | None = None,
    token: str | None = None,
    http_url: str | None = None,
) -> tuple[float | None, dict[str, Any]]:
    """全市场破净股占比(%) — 使用 daily_basic 中 pb<1 的占比估算。"""
    cli = _client(token, http_url)
    try:
        rows = cli.query("daily_basic", params={"trade_date": ""})
        total = 0
        pb_below = 0
        for r in rows:
            pb = r.get("pb")
            if pb is not None:
                total += 1
                try:
                    if float(pb) < 1.0:
                        pb_below += 1
                except (TypeError, ValueError):
                    continue
        if total == 0:
            return None, {"error": "no pb data"}
        ratio = pb_below / total * 100.0
        return ratio, {"pb_below_count": pb_below, "total": total}
    except Exception as e:
        return None, {"error": str(e)}


# ── 维度5: 经济基本面 ───────────────────────────────────────


def fetch_pmi(
    token: str | None = None, http_url: str | None = None
) -> tuple[float | None, dict[str, Any]]:
    """制造业 PMI(%)。"""
    cli = _client(token, http_url)
    try:
        rows = cli.query("cn_pmi", params={})
        if not rows:
            return None, {"error": "no data"}
        val = rows[0].get("value")
        if val is None:
            return None, {"error": "field not found"}
        return float(val), {"source": "tushare.cn_pmi"}
    except Exception as e:
        return None, {"error": str(e)}


def fetch_ppi(
    token: str | None = None, http_url: str | None = None
) -> tuple[float | None, dict[str, Any]]:
    """PPI 同比(%)。"""
    cli = _client(token, http_url)
    try:
        rows = cli.query("cn_ppi", params={})
        if not rows:
            return None, {"error": "no data"}
        val = rows[0].get("value")
        if val is None:
            return None, {"error": "field not found"}
        return float(val), {"source": "tushare.cn_ppi"}
    except Exception as e:
        return None, {"error": str(e)}


def fetch_cpi(
    token: str | None = None, http_url: str | None = None
) -> tuple[float | None, dict[str, Any]]:
    """CPI 同比(%)。"""
    cli = _client(token, http_url)
    try:
        rows = cli.query("cn_cpi", params={})
        if not rows:
            return None, {"error": "no data"}
        val = rows[0].get("value")
        if val is None:
            return None, {"error": "field not found"}
        return float(val), {"source": "tushare.cn_cpi"}
    except Exception as e:
        return None, {"error": str(e)}
