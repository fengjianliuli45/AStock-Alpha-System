from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from astock_alpha.exceptions import GovernanceError, TradingDisabledError
from astock_alpha.modules.m0_governance import GovernanceModule
from astock_alpha.types import PromotionMetrics, StrategyStatus

CONFIG = Path(__file__).resolve().parents[1] / "configs" / "strategy_v1_0.preregistered.json"


def test_freeze_and_detect_mutation():
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    gov = GovernanceModule(cfg)
    gov.freeze_parameters()
    assert gov.parameter_hash

    mutated = deepcopy(cfg)
    mutated["exit"]["hard_stop_pct"] = 0.05
    with pytest.raises(GovernanceError, match="mutation"):
        gov.assert_params_unchanged(mutated)


def test_trading_disabled_by_default():
    gov = GovernanceModule.from_json(CONFIG)
    with pytest.raises(TradingDisabledError):
        gov.assert_trading_allowed()


def test_promotion_gate_and_enable():
    gov = GovernanceModule.from_json(CONFIG)
    bad = PromotionMetrics()
    result = gov.evaluate_promotion_gate(bad)
    assert not result.passed
    assert result.failures

    good = PromotionMetrics(
        oos_rebalance_periods=24,
        normal_cost_return=0.1,
        double_cost_return=0.01,
        max_drawdown=0.1,
        information_ratio=0.6,
        positive_excess_month_ratio=0.56,
        rolling_12m_ir=0.35,
        max_single_factor_alpha_share=0.3,
        test_annual_excess=0.05,
    )
    ok = gov.evaluate_promotion_gate(good)
    assert ok.passed
    assert gov.status == StrategyStatus.PROMOTED
    gov.enable_trading()
    assert gov.trading_enabled
    gov.assert_trading_allowed()


def test_death_line_freezes():
    gov = GovernanceModule.from_json(CONFIG)
    assert gov.record_oos_ir(-0.6) != StrategyStatus.FROZEN_PERMANENTLY
    assert gov.record_oos_ir(-0.7) != StrategyStatus.FROZEN_PERMANENTLY
    assert gov.record_oos_ir(-0.8) == StrategyStatus.FROZEN_PERMANENTLY
    assert gov.trading_enabled is False
