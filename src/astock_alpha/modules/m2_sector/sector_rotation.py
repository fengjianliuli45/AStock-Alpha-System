"""m2_sector 核心逻辑：行业动量轮动 + 分区制板块选择。

对齐 m1 区制：
- BULL: 动量轮动，top3 板块按比例分配
- SIDEWAYS: 双轨制（超跌反弹 / 防御持有）
- BEAR/PANIC: 空仓
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

# ── 行业映射 ─────────────────────────────────────────────
# 从 Tushare stock_basic 拉取，存为 CSV
# 优先使用 repo 内路径，fallback 到外部共享文件夹
_REPO_MAPPING_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "stock_industry_mapping.csv"
_FALLBACK_MAPPING_PATH = Path("/mnt/hgfs/host_downloads/a_share_5y/stock_industry_mapping.csv")
_DEFAULT_MAPPING_PATH = _REPO_MAPPING_PATH if _REPO_MAPPING_PATH.exists() else _FALLBACK_MAPPING_PATH

# ── 默认防御板块池（可被 select_sideways_sectors 的 defensive_pool 参数覆盖）
DEFAULT_DEFENSIVE_POOL: list[str] = [
    "银行", "电力", "水务", "供气供热", "公路", "铁路",
    "机场", "港口", "保险", "黄金",
]


def load_industry_mapping(path: str | Path | None = None) -> dict[str, str]:
    """加载股票代码→行业映射。返回 {symbol: industry_name}。

    symbol 格式为 SHSE.600000 / SZSE.000001
    """
    p = Path(path) if path else _DEFAULT_MAPPING_PATH
    mapping: dict[str, str] = {}
    if not p.exists():
        return mapping
    with open(p, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts = (row.get("ts_code") or "").strip()
            ind = (row.get("industry") or "").strip()
            if ts and ind:
                parts = ts.split(".")
                if len(parts) == 2:
                    raw_code, suffix = parts[0], parts[1].upper()
                    if suffix == "SH":
                        # parquet 中 code 列格式为 "sh.600000"
                        mapping[f"SHSE.{raw_code}"] = ind
                        mapping[f"sh.{raw_code}"] = ind
                    elif suffix == "SZ":
                        mapping[f"SZSE.{raw_code}"] = ind
                        mapping[f"sz.{raw_code}"] = ind
    return mapping


# ── 行业日线聚合 ─────────────────────────────────────────

def compute_daily_industry_returns(
    panel: pd.DataFrame,
    industry_mapping: dict[str, str],
    date_col: str = "date",
    pct_col: str = "pctChg",
    amount_col: str | None = "amount",
) -> pd.DataFrame:
    """从面板数据按行业聚合每日涨跌幅（等权）。

    返回：
        DataFrame，index=date, columns=industry_name, values=等权涨跌幅
    """
    panel = panel.copy()
    # code 列是 "sh.600000" / "sz.000001"，需要标准化
    panel["_sym"] = panel["code"].str.lower()
    # 也尝试构造 full symbol 格式
    panel["_full_sym"] = panel["code"].apply(
        lambda c: f"SHSE.{c.split('.')[1]}" if c.startswith("sh.") else (
            f"SZSE.{c.split('.')[1]}" if c.startswith("sz.") else c
        )
    )
    # 先试 full sym，再试 raw sym
    panel["industry"] = panel["_full_sym"].map(industry_mapping)
    panel["industry"] = panel["industry"].fillna(panel["_sym"].map(industry_mapping))
    # 去掉没行业的股票
    panel = panel[panel["industry"].notna()]

    # 等权：每日每个行业所有股票 pctChg 的平均
    daily_ind = panel.groupby([date_col, "industry"])[pct_col].mean().unstack()
    return daily_ind


def compute_industry_momentum(
    industry_returns: pd.DataFrame,
    window: int = 20,
) -> pd.Series:
    """计算每个行业过去 window 天的动量（累积涨跌幅）。

    对 DataFrame 也可调用，返回最后一行（最近 window 天动量）。
    对 Series 直接返回该 Series 的动量值。
    """
    cum = (1 + industry_returns / 100)
    rolled = cum.rolling(window).apply(lambda x: x.prod() - 1, raw=True)
    if isinstance(industry_returns, pd.DataFrame):
        return rolled.iloc[-1] * 100
    return rolled.iloc[-1] * 100


def compute_industry_volume_growth(
    panel: pd.DataFrame,
    industry_mapping: dict[str, str],
    window: int = 20,
    amount_col: str = "amount",
) -> pd.Series:
    """每个行业过去 window 天的成交额增速（最近 5 天均值 / 前 15 天均值）。"""
    panel = panel.copy()
    panel["industry"] = panel["code"].map(industry_mapping)
    panel = panel[panel["industry"].notna()]

    # 用每只股票amount求和，按industry groupby
    daily_vol_pivot = panel.groupby(["date", "industry"])[amount_col].sum().unstack()
    if daily_vol_pivot.empty:
        return pd.Series(dtype=float)
    
    vol_ma5 = daily_vol_pivot.tail(5).mean()
    vol_ma20 = daily_vol_pivot.mean()
    growth = (vol_ma5 / vol_ma20 - 1) * 100
    return growth.fillna(0)


# ── 分区制板块选择 ──────────────────────────────────────

@dataclass
class SectorAllocation:
    industries: list[str]  # 选中的行业
    weights: list[float]   # 对应的仓位占比（和为1）
    total_industries: int = 3

    def to_dict(self) -> dict[str, Any]:
        return {"industries": self.industries, "weights": self.weights}


def _filter_uptrend(
    industries: list[str],
    industry_returns: pd.DataFrame,
    ma_window: int = 20,
    trend_confirm: int = 3,
) -> list[str]:
    """过滤出站上 MA20 且 MA 上行的行业。"""
    if industry_returns.empty:
        return industries
    # 计算 cum return for MA
    cum = (1 + industry_returns / 100).cumprod()
    ma = cum.rolling(ma_window).mean()
    valid = []
    for ind in industries:
        if ind not in ma.columns:
            continue
        ind_ma = ma[ind].dropna()
        if len(ind_ma) < trend_confirm:
            continue
        # MA20 连续 3 日上行
        recent = ind_ma.iloc[-trend_confirm:]
        if not (recent.diff().dropna() > 0).all():
            continue
        # 价格 > MA20
        if cum[ind].iloc[-1] < ind_ma.iloc[-1]:
            continue
        valid.append(ind)
    return valid


def select_bull_sectors(
    industry_returns: pd.DataFrame,
    momentum: pd.Series,
    volume_growth: pd.Series | None = None,
    hs300_momentum: float = 0.0,
    top_n: int = 3,
    verbose: bool = False,
) -> SectorAllocation:
    """BULL 区：动量轮动，选 top N 板块。

    综合评分：
    - 动量强度（近 20 日涨跌幅，权重 60%）
    - 成交额增速（权重 20%）
    - 相对沪深300 超额（权重 20%）
    """
    candidates: list[tuple[str, float]] = []

    for ind in momentum.index:
        if pd.isna(momentum[ind]):
            continue
        score = 0.0
        # 动量 60%
        score += momentum[ind] * 0.6
        # 成交额增速 20%
        if volume_growth is not None and ind in volume_growth.index:
            score += volume_growth[ind] * 0.2
        # 相对沪深300 超额 20%
        excess = momentum[ind] - hs300_momentum
        score += excess * 0.2
        candidates.append((ind, score))

    candidates.sort(key=lambda x: x[1], reverse=True)

    # 趋势过滤
    selected = [c[0] for c in candidates[:top_n * 2]]
    selected = _filter_uptrend(selected, industry_returns)
    selected = selected[:top_n]

    if not selected:
        # 全无趋势，取动量最好的
        selected = [c[0] for c in candidates[:top_n]]

    # 分配权重（激进版：第1 40%/第2 35%/第3 25%）
    weights_dict = {0: 0.40, 1: 0.35, 2: 0.25}
    weights = [weights_dict.get(i, 1.0 / len(selected)) for i in range(len(selected))]
    # 归一化
    total_w = sum(weights)
    weights = [w / total_w for w in weights]

    if verbose:
        print(f"  BULL 轮动: 选 {len(selected)}/{len(candidates)} 行业")
        for ind, w in zip(selected, weights):
            mom = momentum.get(ind, 0)
            print(f"    {ind}: 动量={mom:.1f}%, 仓位={w:.0%}")

    return SectorAllocation(industries=selected, weights=weights)


def select_sideways_sectors(
    industry_returns: pd.DataFrame,
    momentum: pd.Series,
    mode: str = "defensive",
    defensive_pool: list[str] | None = None,
    verbose: bool = False,
) -> SectorAllocation:
    """SIDEWAYS 区：双轨制。

    mode='oversold': 超跌反弹 — 近20日跌幅前5 + RSI ≤ 30
    mode='defensive': 防御持有 — 固定防御池（可通过 defensive_pool 参数覆盖）
    """
    pool = defensive_pool if defensive_pool is not None else DEFAULT_DEFENSIVE_POOL

    if mode == "oversold":
        # 找超跌行业
        losers = momentum.sort_values().head(10)
        candidates = [(ind, mom) for ind, mom in losers.items() if mom < -10]
        candidates = candidates[:2]
        if not candidates:
            # 没有超跌，fallback 到防御
            return select_sideways_sectors(industry_returns, momentum, "defensive", verbose)
        selected = [c[0] for c in candidates]
        weights = [0.5, 0.5]
    else:
        # 防御持有：从防御池里找当天有数据的
        available = [ind for ind in pool if ind in momentum.index]
        selected = available[:3]
        weights = [1.0 / len(selected)] * len(selected) if selected else []

    if verbose:
        print(f"  SIDEWAYS({mode}): {selected} 各 {weights}")

    return SectorAllocation(industries=selected, weights=weights)


def select_panic_sectors() -> SectorAllocation:
    """BEAR/PANIC 区：空仓"""
    return SectorAllocation(industries=[], weights=[])


# ── 主入口 ───────────────────────────────────────────────

def compute_sector_allocation(
    m1_regime: str,
    m1_position_multiplier: float,
    panel: pd.DataFrame,
    industry_mapping: dict[str, str] | None = None,
    index_returns: pd.DataFrame | None = None,
    verbose: bool = False,
) -> dict[str, Any]:
    """根据 m1 区制和当日面板数据，输出行业配置。

    返回：
        {
            "industries": [str],        # 选中行业列表
            "weights": [float],         # 各行业在总仓位内的占比（和为1）
            "total_position": float,    # 实际总仓位（m1上限 × 行业配置系数）
        }
    """
    if industry_mapping is None:
        industry_mapping = load_industry_mapping()

    if m1_regime in ("bear", "panic"):
        result = select_panic_sectors()
        pos = 0.0
        return {
            "industries": result.industries,
            "weights": result.weights,
            "total_position": pos,
        }

    # 行业日线数据
    ind_rets = compute_daily_industry_returns(panel, industry_mapping)
    if ind_rets.empty:
        return {
            "industries": [],
            "weights": [],
            "total_position": m1_position_multiplier,
        }

    momentum = compute_industry_momentum(ind_rets, window=20)
    # 成交额增速
    vol_growth = compute_industry_volume_growth(panel, industry_mapping)

    # 沪深300 动量（用于超额收益评分）
    hs300_momentum = 0.0
    if index_returns is not None:
        hs300_momentum = compute_industry_momentum(index_returns.to_frame("hs300"), window=20).iloc[0]

    if m1_regime == "bull":
        result = select_bull_sectors(
            ind_rets, momentum, vol_growth,
            hs300_momentum=hs300_momentum,
            verbose=verbose
        )
        pos = m1_position_multiplier
    elif m1_regime == "sideways":
        # 简单策略：先试防守，如果动量区制内有超跌则用超跌
        mode = "defensive"
        # 如果有行业跌幅超过 -10% 则用超跌模式
        worst = momentum.min() if not momentum.empty else 0
        if not pd.isna(worst) and worst < -10:
            mode = "oversold"
        result = select_sideways_sectors(
            ind_rets, momentum, mode=mode,
            verbose=verbose
        )
        pos = m1_position_multiplier
    else:
        result = select_panic_sectors()
        pos = 0.0

    return {
        "industries": result.industries,
        "weights": result.weights,
        "total_position": pos,
    }
