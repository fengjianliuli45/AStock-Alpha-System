"""Tushare 宏观数据采集器 — 供 m2_market_environment 使用。

每个函数返回 (value: float | None, detail: dict)，失败返回 (None, {"error": str})。
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from astock_alpha.data.tushare_client import (
    TushareHttpClient,
    load_tushare_token,
    DEFAULT_TOKEN_PATH,
    DEFAULT_HTTP_URL,
)


def _client(token_path: str | None = None) -> TushareHttpClient:
    return TushareHttpClient(
        token_path=token_path or str(DEFAULT_TOKEN_PATH),
        http_url=DEFAULT_HTTP_URL,
    )


def _last_n_trade_days(asof: date, n: int) -> date:
    """粗略往前推 N 个自然日（用于宏观历史）。"""
    return asof - timedelta(days=n * 2)


# ── 维度1: 货币流动性 ─────────────────────────────────────────


def fetch_m1_growth(token_path: str | None = None) -> tuple[float | None, dict[str, Any]]:
    """M1 同比增速（最近一条）。"""
    try:
        c = _client(token_path)
        rows = c.query("money_supply", params={"m": "M1"}, fields="m,yoy")
        if not rows:
            return None, {"error": "no M1 data"}
        yoy = float(rows[0].get("yoy", 0))
        return yoy, {"latest": rows[0].get("m"), "detail": rows[0]}
    except Exception as e:
        return None, {"error": str(e)}


def fetch_m1_m2_spread(token_path: str | None = None) -> tuple[float | None, dict[str, Any]]:
    """M1 同比 - M2 同比，最近一条。"""
    try:
        c = _client(token_path)
        m1_rows = c.query("money_supply", params={"m": "M1"}, fields="m,yoy")
        m2_rows = c.query("money_supply", params={"m": "M2"}, fields="m,yoy")
        if not m1_rows or not m2_rows:
            return None, {"error": "no M1/M2 data"}
        spread = float(m1_rows[0]["yoy"]) - float(m2_rows[0]["yoy"])
        return spread, {"m1_yoy": m1_rows[0]["yoy"], "m2_yoy": m2_rows[0]["yoy"]}
    except Exception as e:
        return None, {"error": str(e)}


def fetch_dr007_20d_avg(
    asof: date | None = None, token_path: str | None = None
) -> tuple[float | None, dict[str, Any]]:
    """DR007 近 20 个交易日均值。"""
    try:
        c = _client(token_path)
        end = (asof or date.today()).strftime("%Y%m%d")
        start = _last_n_trade_days(asof or date.today(), 30).strftime("%Y%m%d")
        rows = c.query("shibor", params={"start_date": start, "end_date": end}, fields="date,1w")
        values = [float(r["1w"]) for r in rows if r.get("1w") not in (None, "")]
        if not values:
            return None, {"error": "no DR007 data"}
        avg = sum(values) / len(values)
        return avg, {"count": len(values), "min": min(values), "max": max(values)}
    except Exception as e:
        return None, {"error": str(e)}


def fetch_social_financing(token_path: str | None = None) -> tuple[float | None, dict[str, Any]]:
    """社融存量同比 ↗（最近一条）。"""
    try:
        c = _client(token_path)
        rows = c.query("cn_m", params={"m": "社会融资规模存量"}, fields="m,yoy")
        if not rows:
            return None, {"error": "no social financing data"}
        return float(rows[0]["yoy"]), {"detail": rows[0]}
    except Exception as e:
        return None, {"error": str(e)}


# ── 维度2: 场内资金面 ─────────────────────────────────────────


def fetch_north_bound_flow(
    n_days: int = 20, asof: date | None = None, token_path: str | None = None
) -> tuple[float | None, dict[str, Any]]:
    """北向资金近 N 日累计净流入（万元）。"""
    try:
        c = _client(token_path)
        end = (asof or date.today()).strftime("%Y%m%d")
        start = _last_n_trade_days(asof or date.today(), n_days + 20).strftime("%Y%m%d")
        rows = c.query("moneyflow_hsgt", params={"start_date": start, "end_date": end}, fields="date,north_money")
        values = [float(r["north_money"]) for r in rows if r.get("north_money") not in (None, "")]
        if not values:
            return None, {"error": "no north flow data"}
        total = sum(values[-n_days:])
        return total, {"count": min(len(values[-n_days:]), n_days), "detail": {"sum_wan": total}}
    except Exception as e:
        return None, {"error": str(e)}


def fetch_margin_balance_growth(
    n_days: int = 20, asof: date | None = None, token_path: str | None = None
) -> tuple[float | None, dict[str, Any]]:
    """融资余额近 N 日增速（百分比变化率）。"""
    try:
        c = _client(token_path)
        end = (asof or date.today()).strftime("%Y%m%d")
        start = _last_n_trade_days(asof or date.today(), n_days + 30).strftime("%Y%m%d")
        rows = c.query("margin", params={"start_date": start, "end_date": end}, fields="trade_date,margin_bal")
        values = [float(r["margin_bal"]) for r in rows if r.get("margin_bal") not in (None, "")]
        if len(values) < n_days + 1:
            return None, {"error": f"not enough margin data (got {len(values)}, need {n_days}+1)"}
        old = values[-(n_days + 1)]
        new = values[-1]
        growth = (new - old) / old * 100 if old != 0 else 0.0
        return growth, {"old_bal": old, "new_bal": new}
    except Exception as e:
        return None, {"error": str(e)}


def fetch_market_volume_avg(
    n_days: int = 5, asof: date | None = None, token_path: str | None = None
) -> tuple[float | None, dict[str, Any]]:
    """两市近 N 日日均成交额（亿元）。取沪深两市每日 total 求和后均值。"""
    try:
        c = _client(token_path)
        end = (asof or date.today()).strftime("%Y%m%d")
        start = _last_n_trade_days(asof or date.today(), n_days + 10).strftime("%Y%m%d")
        rows = c.query("trade_cal", params={"start_date": start, "end_date": end, "exchange": "SSE"}, fields="cal_date,is_open")
        cal_dates = [r["cal_date"] for r in rows if r.get("is_open") == "1"][-n_days:]
        if not cal_dates:
            return None, {"error": "no trading days found"}

        totals = []
        for td in cal_dates:
            r = c.query("daily", params={"trade_date": td}, fields="ts_code,amount")
            if r:
                amt = sum(float(x["amount"]) for x in r if x.get("amount") not in (None, ""))
                totals.append(amt / 1e8)  # 元 → 亿元
        if not totals:
            return None, {"error": "no volume data"}
        return sum(totals) / len(totals), {"count": len(totals), "daily_amounts": totals}
    except Exception as e:
        return None, {"error": str(e)}


def fetch_main_capital_flow(
    n_days: int = 5, asof: date | None = None, token_path: str | None = None
) -> tuple[float | None, dict[str, Any]]:
    """主力资金近 N 日累计净额（万元）。用 moneyflow_hsgt 代替全市场。"""
    try:
        c = _client(token_path)
        end = (asof or date.today()).strftime("%Y%m%d")
        start = _last_n_trade_days(asof or date.today(), n_days + 10).strftime("%Y%m%d")
        rows = c.query("moneyflow_hsgt", params={"start_date": start, "end_date": end}, fields="date,hsgt")
        values = [float(r["hsgt"]) for r in rows if r.get("hsgt") not in (None, "")]
        if not values:
            return None, {"error": "no main capital flow data"}
        total = sum(values[-n_days:])
        return total, {"count": min(len(values[-n_days:]), n_days), "sum_wan": total}
    except Exception as e:
        return None, {"error": str(e)}


# ── 维度3: 全市场估值水位 ──────────────────────────────────────


def fetch_market_pe_percentile(token_path: str | None = None) -> tuple[float | None, dict[str, Any]]:
    """全市场 PE-TTM 分位（万得全A 近 10 年分位）。
    使用沪深300 PE-TTM 近似。
    """
    try:
        c = _client(token_path)
        rows = c.query("index_daily", params={"ts_code": "000300.SH", "start_date": "20160720", "end_date": date.today().strftime("%Y%m%d")}, fields="trade_date,pe_ttm")
        pe_values = [float(r["pe_ttm"]) for r in rows if r.get("pe_ttm") not in (None, "")]
        if not pe_values:
            return None, {"error": "no PE data"}
        current = pe_values[-1]
        rank = sum(1 for x in pe_values if x <= current) / len(pe_values)
        return rank * 100, {"current_pe": current, "pe_10y_low": min(pe_values), "pe_10y_high": max(pe_values)}
    except Exception as e:
        return None, {"error": str(e)}


def fetch_risk_premium(token_path: str | None = None) -> tuple[float | None, dict[str, Any]]:
    """风险溢价（1/PE - 10Y国债收益率）的分位秩。"""
    try:
        c = _client(token_path)
        # PE
        pe_rows = c.query("index_daily", params={"ts_code": "000300.SH", "start_date": "20160720", "end_date": date.today().strftime("%Y%m%d")}, fields="trade_date,pe_ttm")
        # 国债 — 用 shibor/债券接口，Tushare 债券数据可能有限
        # 这里用 10 年期国债收益率（cn_10ybond 或 yc）
        bond_rows = c.query("yc", params={"curve": "0", "start_date": "20160720", "end_date": date.today().strftime("%Y%m%d")}, fields="trade_date,yeild_10")
        if not pe_rows or not bond_rows:
            return None, {"error": "no PE or bond data"}
        pe_list = [float(r["pe_ttm"]) for r in pe_rows if r.get("pe_ttm") not in (None, "")]
        bond_list = [float(r["yeild_10"]) for r in bond_rows if r.get("yeild_10") not in (None, "")]
        if not pe_list or not bond_list:
            return None, {"error": "empty PE or bond series"}
        min_len = min(len(pe_list), len(bond_list))
        risk_premia = [1.0 / pe_list[-i] - bond_list[-i] / 100 for i in range(1, min_len + 1)]
        current = risk_premia[-1]
        rank = sum(1 for x in risk_premia if x <= current) / len(risk_premia)
        return rank * 100, {"current_risk_premium": current, "count": len(risk_premia)}
    except Exception as e:
        return None, {"error": str(e)}


def fetch_lot_break_ratio(
    asof: date | None = None, token_path: str | None = None
) -> tuple[float | None, dict[str, Any]]:
    """破净股占比（PB<1 股票数/总股票数）。Tushare 用 daily_basic 全市场扫描。"""
    try:
        c = _client(token_path)
        td = (asof or date.today()).strftime("%Y%m%d")
        rows = c.query("daily_basic", params={"trade_date": td}, fields="ts_code,pb")
        if not rows:
            return None, {"error": "no daily_basic data"}
        total = len(rows)
        if total == 0:
            return None, {"error": "empty daily_basic"}
        pb_below_1 = sum(1 for r in rows if r.get("pb") not in (None, "") and float(r["pb"]) < 1.0)
        ratio = pb_below_1 / total * 100
        return ratio, {"total_stocks": total, "below_pb_1": pb_below_1}
    except Exception as e:
        return None, {"error": str(e)}


# ── 维度4: 市场情绪（从 m1 直接读，此处不采集） ────────────────


# ── 维度5: 经济基本面 ─────────────────────────────────────────


def fetch_pmi(token_path: str | None = None) -> tuple[float | None, dict[str, Any]]:
    """制造业 PMI。"""
    try:
        c = _client(token_path)
        rows = c.query("cn_pmi", params={"m": "制造业"}, fields="m,val")
        if not rows:
            return None, {"error": "no PMI data"}
        return float(rows[0]["val"]), {"detail": rows[0]}
    except Exception as e:
        return None, {"error": str(e)}


def fetch_ppi(token_path: str | None = None) -> tuple[float | None, dict[str, Any]]:
    """PPI 同比。"""
    try:
        c = _client(token_path)
        rows = c.query("cn_ppi", params={"m": "全部工业品"}, fields="m,yoy")
        if not rows:
            rows = c.query("cn_ppi", fields="m,yoy")
        if not rows:
            return None, {"error": "no PPI data"}
        return float(rows[0]["yoy"]), {"detail": rows[0]}
    except Exception as e:
        return None, {"error": str(e)}


def fetch_cpi(token_path: str | None = None) -> tuple[float | None, dict[str, Any]]:
    """CPI 同比。"""
    try:
        c = _client(token_path)
        rows = c.query("cn_cpi", fields="m,yoy")
        if not rows:
            return None, {"error": "no CPI data"}
        return float(rows[0]["yoy"]), {"detail": rows[0]}
    except Exception as e:
        return None, {"error": str(e)}
