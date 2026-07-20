"""m2_market_environment — 大盘环境综合评分主模块。"""

from __future__ import annotations

import logging
from typing import Any

from astock_alpha.data.tushare_macro import (
    fetch_cpi,
    fetch_dr007_20d_avg,
    fetch_lot_break_ratio,
    fetch_m1_growth,
    fetch_m1_m2_spread,
    fetch_main_capital_flow,
    fetch_margin_balance_growth,
    fetch_market_pe_percentile,
    fetch_market_volume_avg,
    fetch_north_bound_flow,
    fetch_pmi,
    fetch_ppi,
    fetch_risk_premium,
    fetch_social_financing,
)
from astock_alpha.modules.base import StrategyModule
from astock_alpha.modules.m2_market_environment.dimensions.capital import score_capital
from astock_alpha.modules.m2_market_environment.dimensions.fundamentals import (
    score_fundamentals,
)
from astock_alpha.modules.m2_market_environment.dimensions.liquidity import score_liquidity
from astock_alpha.modules.m2_market_environment.dimensions.sentiment import score_sentiment
from astock_alpha.modules.m2_market_environment.dimensions.valuation import score_valuation
from astock_alpha.modules.m2_market_environment.scoring import (
    EnvironmentScore,
    compute_environment_score,
)
from astock_alpha.types import PipelineState

logger = logging.getLogger(__name__)


class MarketEnvironmentModule(StrategyModule):
    """Module 2: 五大维度大盘环境综合评分。

    在 m1 (regime) 之前运行，产出 EnvironmentScore → state.meta["m2_environment"]。
    m3 根据环境评级选择不同的股票池过滤条件。
    """

    name = "market_environment"
    module_id = "m2_market_environment"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        m2_cfg = (self.config or {}).get("modules", {}).get("m2_market_environment", {})
        self.weights = m2_cfg.get("weights", None)  # None → 默认权重
        self.token_path = str(
            (self.config or {}).get("data", {}).get("tushare_token_path", "")
        ) or None

    def is_ready(self) -> bool:
        return True  # 没有就是 None 降级，不会崩溃

    def run(self, state: PipelineState) -> PipelineState:
        audit: dict[str, Any] = {}
        dimension_scores: dict[str, float | None] = {}
        dimension_details: dict[str, Any] = {}

        # ── 维度1: 货币流动性 ──
        liquidity_data: dict[str, Any] = {}
        m1v, m1d = fetch_m1_growth(self.token_path)
        liquidity_data["m1_growth_value"] = m1v
        spread_v, spread_d = fetch_m1_m2_spread(self.token_path)
        liquidity_data["m1_m2_spread_value"] = spread_v
        dr_v, dr_d = fetch_dr007_20d_avg(state.asof, self.token_path)
        liquidity_data["dr007_20d_avg_value"] = dr_v
        sf_v, sf_d = fetch_social_financing(self.token_path)
        liquidity_data["social_financing_value"] = sf_v
        liq_score, liq_detail = score_liquidity(liquidity_data)
        dimension_scores["liquidity"] = liq_score
        dimension_details["liquidity"] = liq_detail
        audit["liquidity_raw"] = {"m1_growth": m1v, "m1_m2_spread": spread_v,
                                  "dr007": dr_v, "social_financing": sf_v}

        # ── 维度2: 场内资金面 ──
        cap_data: dict[str, Any] = {}
        nf_v, nf_d = fetch_north_bound_flow(asof=state.asof, token_path=self.token_path)
        cap_data["north_flow_value"] = nf_v
        mg_v, mg_d = fetch_margin_balance_growth(asof=state.asof, token_path=self.token_path)
        cap_data["margin_growth_value"] = mg_v
        vol_v, vol_d = fetch_market_volume_avg(asof=state.asof, token_path=self.token_path)
        cap_data["volume_avg_value"] = vol_v
        mcf_v, mcf_d = fetch_main_capital_flow(asof=state.asof, token_path=self.token_path)
        cap_data["main_capital_flow_value"] = mcf_v
        cap_score, cap_detail = score_capital(cap_data)
        dimension_scores["capital"] = cap_score
        dimension_details["capital"] = cap_detail
        audit["capital_raw"] = {"north_flow": nf_v, "margin_growth": mg_v,
                                "volume": vol_v, "main_capital": mcf_v}

        # ── 维度3: 估值水位 ──
        val_data: dict[str, Any] = {}
        pe_v, pe_d = fetch_market_pe_percentile(self.token_path)
        val_data["pe_percentile_value"] = pe_v
        rp_v, rp_d = fetch_risk_premium(self.token_path)
        val_data["risk_premium_value"] = rp_v
        lbr_v, lbr_d = fetch_lot_break_ratio(state.asof, self.token_path)
        val_data["lot_break_ratio_value"] = lbr_v
        val_score, val_detail = score_valuation(val_data)
        dimension_scores["valuation"] = val_score
        dimension_details["valuation"] = val_detail
        audit["valuation_raw"] = {"pe_percentile": pe_v, "risk_premium": rp_v,
                                  "lot_break_ratio": lbr_v}

        # ── 维度4: 情绪（从 m1 读）──
        m1_sent = state.meta.get("sentiment")
        sen_score, sen_detail = score_sentiment(m1_sent)
        dimension_scores["sentiment"] = sen_score
        dimension_details["sentiment"] = sen_detail
        audit["sentiment_raw"] = {"from_m1": bool(m1_sent)}

        # ── 维度5: 经济基本面 ──
        fund_data: dict[str, Any] = {}
        pmi_v, pmi_d = fetch_pmi(self.token_path)
        fund_data["pmi_value"] = pmi_v
        ppi_v, ppi_d = fetch_ppi(self.token_path)
        fund_data["ppi_value"] = ppi_v
        cpi_v, cpi_d = fetch_cpi(self.token_path)
        fund_data["cpi_value"] = cpi_v
        fund_score, fund_detail = score_fundamentals(fund_data)
        dimension_scores["fundamentals"] = fund_score
        dimension_details["fundamentals"] = fund_detail
        audit["fundamentals_raw"] = {"pmi": pmi_v, "ppi": ppi_v, "cpi": cpi_v}

        # ── 综合打分 ──
        env = compute_environment_score(
            dimension_scores,
            weights=self.weights,
            dimension_details=dimension_details,
        )
        state.meta["m2_environment"] = env.to_dict()
        state.meta["m2_audit"] = audit

        if env.rating in ("BEAR_STRONG", "BEAR_WEAK"):
            state.warnings.append(f"m2_market_environment: {env.rating} ({env.composite_score:.1f})")
        return state
