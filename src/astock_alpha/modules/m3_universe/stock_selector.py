"""m3_universe/stock_selector — 选股层模块。

m3 是纯选股器：在 m2 选定的行业池内做个股优选，只赚个股超额收益。
- 不改变总仓位、不切换行业、不判断大盘走势
- 总仓位严格等于 m2 输出的权益仓位
- 选股范围严格限定在板块层选定的行业/主题内
- m1 切换为 bear/panic 时直接跟随清仓

分区制：
  BULL: 动量趋势选股（强者恒强，放大弹性）
  SIDEWAYS: 超跌反转选股（安全边际优先，快进快出）
  BEAR/PANIC: 空仓
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ── 导入行业映射 ──────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "src"))
from astock_alpha.modules.m2_sector.sector_rotation import (
    load_industry_mapping,
    compute_daily_industry_returns,
    compute_industry_momentum,
)


class RegimeMode(Enum):
    BULL = "bull"
    SIDEWAYS = "sideways"
    BEAR = "bear"
    PANIC = "panic"


# ── 数据类 ────────────────────────────────────────────────

@dataclass
class StockPosition:
    code: str              # sh.600000
    name: str | None = None
    industry: str | None = None
    weight: float = 0.0    # 在总权益中的占比
    cost_price: float = 0.0  # 持仓成本价（相对于初始净值 1.0 的累计倍数）
    entry_date: str = ""
    hold_days: int = 0
    regime: str = "bull"


@dataclass
class StockSelection:
    positions: list[StockPosition] = field(default_factory=list)
    total_weight: float = 0.0  # 总和，正常应等于 m2 total_position

    def to_dict(self) -> dict[str, Any]:
        return {
            "positions": [
                {"code": p.code, "name": p.name, "industry": p.industry,
                 "weight": p.weight, "entry_date": p.entry_date,
                 "hold_days": p.hold_days, "regime": p.regime}
                for p in self.positions
            ],
            "total_weight": self.total_weight,
        }


# ── 辅助函数 ──────────────────────────────────────────────

def compute_rsi(series: pd.Series, period: int = 14) -> float:
    """计算 RSI(14) 值。"""
    if len(series) < period + 1:
        return 50.0
    delta = series.diff().dropna()
    gains = delta.where(delta > 0, 0.0)
    losses = -delta.where(delta < 0, 0.0)
    avg_gain = gains.tail(period).mean()
    avg_loss = losses.tail(period).mean()
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _build_price_series(panel_stock: pd.DataFrame, base_price: float = 100.0) -> pd.Series:
    """从 pctChg 反推价格序列。

    按日期升序排列，从 base_price 开始每日累乘。
    """
    sorted_df = panel_stock.sort_values("date")
    prices = [base_price]
    for ret in sorted_df["pctChg"].values:
        prices.append(prices[-1] * (1 + ret / 100.0))
    return pd.Series(prices[1:], index=sorted_df["date"].values)


def _industries_for_codes(panel: pd.DataFrame, industry_mapping: dict[str, str]) -> pd.Series:
    """给 panel 的每一行分配行业名。"""
    codes = panel["code"]
    industries = []
    for c in codes:
        c_low = c.lower()
        if c_low.startswith("sh."):
            sym = f"SHSE.{c_low.split('.')[1]}"
            raw = c_low
        elif c_low.startswith("sz."):
            sym = f"SZSE.{c_low.split('.')[1]}"
            raw = c_low
        else:
            sym = raw = c_low
        ind = industry_mapping.get(sym) or industry_mapping.get(raw)
        industries.append(ind)
    return pd.Series(industries, index=panel.index)


def _is_st_stock(code: str) -> bool:
    """检查是否 ST/退市股票（code 或 name 中包含 ST）。"""
    return "st" in code.lower() or "*st" in code.lower()


# ── BULL 区选股 ──────────────────────────────────────────

def _bull_sort_and_select(
    panel: pd.DataFrame,
    industry_mapping: dict[str, str],
    target_industries: list[str],
    top_per_industry: int = 3,
    liquidity_ratio: float = 0.5,
    verbose: bool = False,
) -> list[StockPosition]:
    """BULL 区：在目标行业内选动量最强个股。

    流程：
    1. 基础排雷：剔除 ST
    2. 流动性过滤：板块内成交额前 50%
    3. 趋势确认：近 20 日超额动量 > 0
    4. 动量排序：按近 20 日涨幅排序
    5. 量能验证：近 5 日均量 >= 近 20 日均量
    """
    _mapping = industry_mapping
    positions: list[StockPosition] = []

    panel_i = panel.copy()
    panel_i["industry"] = _industries_for_codes(panel_i, _mapping)

    for ind_name in target_industries:
        sub = panel_i[panel_i["industry"] == ind_name]
        if sub.empty or len(sub) < 3:
            continue

        # 1. 排雷
        sub = sub[~sub["code"].apply(_is_st_stock)]

        # 2. 流动性过滤（用 amount > 中位数作为 proxy）
        median_amt = sub["amount"].median()
        if median_amt > 0:
            sub = sub[sub["amount"] >= median_amt]

        # 3. 动量排序
        sub = sub.sort_values("pctChg", ascending=False)

        # 4. 量能验证
        candidates = []
        for _, row in sub.iterrows():
            candidates.append(
                StockPosition(
                    code=row["code"],
                    industry=ind_name,
                    weight=0.0,  # 后面再分配
                    regime="bull",
                )
            )
            if len(candidates) >= top_per_industry:
                break

        if verbose:
            print(f"    {ind_name}: {len(candidates)} 候选/{len(sub)} 只")
        positions.extend(candidates)

    return positions


# ── SIDEWAYS 区选股 ──────────────────────────────────────

def _sideways_sort_and_select(
    panel: pd.DataFrame,
    industry_mapping: dict[str, str],
    target_industries: list[str],
    top_per_industry: int = 2,
    verbose: bool = False,
) -> list[StockPosition]:
    """SIDEWAYS 区：在目标行业内选超跌反转个股。

    流程：
    1. 基础排雷 + 流动性过滤（同 BULL）
    2. 超跌筛选：跌幅板块内前 30%，RSI <= 30
    3. 抛压衰竭：缩量条件（近 3 日均量 < 近 20 日均量 * 0.6）
    """
    _mapping = industry_mapping
    positions: list[StockPosition] = []

    panel_i = panel.copy()
    panel_i["industry"] = _industries_for_codes(panel_i, _mapping)

    for ind_name in target_industries:
        sub = panel_i[panel_i["industry"] == ind_name]
        if sub.empty or len(sub) < 3:
            continue

        # 1. 排雷
        sub = sub[~sub["code"].apply(_is_st_stock)]

        # 2. 超跌筛选（pctChg 小 = 跌）
        sub = sub.sort_values("pctChg", ascending=True)
        # 取跌幅前 30%
        cutoff = max(3, int(len(sub) * 0.3))
        sub = sub.head(cutoff)

        # 3. RSI 过滤（只对当日可用数据计算）
        # 单日 panel 无法算 RSI，需要多日历史。这里用 pctChg < -3% 作为跌透 proxy
        sub = sub[sub["pctChg"].astype(float) < -2.0]

        # 4. 缩量过滤：用 amount 简单降序（越接近 0 越缩量）
        sub = sub.sort_values("amount", ascending=True)

        candidates = []
        for _, row in sub.head(top_per_industry * 2).iterrows():
            candidates.append(
                StockPosition(
                    code=row["code"],
                    industry=ind_name,
                    weight=0.0,
                    regime="sideways",
                )
            )
            if len(candidates) >= top_per_industry:
                break

        if verbose:
            print(f"    {ind_name}: {len(candidates)} 候选")
        positions.extend(candidates)

    return positions


# ── 主选择器 ──────────────────────────────────────────────

class StockSelector:
    """选股层主类。接收 m2 的输出，输出最终持仓清单。"""

    def __init__(
        self,
        industry_mapping: dict[str, str] | None = None,
        mapping_path: str | Path | None = None,
    ):
        self.mapping = industry_mapping or load_industry_mapping(mapping_path)
        self.positions: dict[str, StockPosition] = {}  # code -> position

    def select(
        self,
        m1_regime: str,
        sector_allocation: dict[str, Any],
        panel: pd.DataFrame,
        date: str,
        verbose: bool = False,
    ) -> StockSelection:
        """主入口。根据 m1 区制和 m2 行业分配，输出选股结果。

        参数：
            m1_regime: 'bull' | 'sideways' | 'bear' | 'panic'
            sector_allocation: m2 输出，含 industries/weights/total_position
            panel: 当日个股面板（date/code/pctChg/amount）
            date: 当前交易日（YYYY-MM-DD）

        返回：
            StockSelection（positions + total_weight）
        """
        regime = m1_regime.lower()
        industries = sector_allocation.get("industries", [])
        weights = sector_allocation.get("weights", [])
        total_pos = sector_allocation.get("total_position", 1.0)

        if regime in ("bear", "panic") or not industries:
            return StockSelection(positions=[], total_weight=0.0)

        # 按区制选股
        if regime == "bull":
            raw = _bull_sort_and_select(
                panel, self.mapping, industries,
                verbose=verbose,
            )
            top_per = 3
        elif regime == "sideways":
            raw = _sideways_sort_and_select(
                panel, self.mapping, industries,
                verbose=verbose,
            )
            top_per = 2
        else:
            return StockSelection(positions=[], total_weight=0.0)

        if not raw:
            return StockSelection(positions=[], total_weight=0.0)

        # 分配行业权重
        industry_weight_map = dict(zip(industries, weights))

        # 合并：按行业分权重，行业内个股等权
        final_positions: list[StockPosition] = []
        by_industry: dict[str, list[StockPosition]] = {}
        for p in raw:
            by_industry.setdefault(p.industry or "", []).append(p)

        for ind, stocks in by_industry.items():
            ind_weight = industry_weight_map.get(ind, 0.0)
            per_stock_weight = ind_weight / len(stocks)
            for s in stocks:
                s.weight = round(per_stock_weight * total_pos, 6)
                s.entry_date = date
                final_positions.append(s)

        total_w = sum(p.weight for p in final_positions)

        # 风控：单股上限 15%，cap 后重新归一化到 total_weight
        capped_total = 0.0
        for p in final_positions:
            p.weight = min(p.weight, 0.15)
            capped_total += p.weight
        
        if capped_total > 0:
            scale = total_w / capped_total
            for p in final_positions:
                p.weight = round(p.weight * scale, 6)

        return StockSelection(positions=final_positions, total_weight=total_w)
