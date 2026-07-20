"""Tests for m2_market_environment module."""

from __future__ import annotations

from astock_alpha.modules.m2_market_environment.scoring import (
    EnvironmentScore,
    compute_environment_score,
)


# ── 打分引擎测试 ──


def test_all_dimensions_bull():
    dims = {"liquidity": 80.0, "capital": 75.0, "valuation": 85.0,
            "sentiment": 70.0, "fundamentals": 65.0}
    env = compute_environment_score(dims)
    assert env.composite_score >= 70
    assert env.rating == "BULL_STRONG"
    assert isinstance(env.to_dict(), dict)
    assert env.to_dict()["rating"] == "BULL_STRONG"


def test_all_dimensions_bear():
    dims = {"liquidity": 15.0, "capital": 20.0, "valuation": 10.0,
            "sentiment": 25.0, "fundamentals": 30.0}
    env = compute_environment_score(dims)
    assert env.composite_score <= 30
    assert env.rating == "BEAR_STRONG"


def test_mixed_mid_range():
    dims = {"liquidity": 50.0, "capital": 40.0, "valuation": 60.0,
            "sentiment": 55.0, "fundamentals": 45.0}
    env = compute_environment_score(dims)
    assert 30 < env.composite_score < 70
    assert env.rating == "BULL_WEAK" or env.rating == "BEAR_WEAK"


def test_partial_dimensions():
    dims = {"liquidity": 80.0, "capital": None, "valuation": None,
            "sentiment": 90.0, "fundamentals": None}
    env = compute_environment_score(dims)
    # only liquidity + sentiment count, both high → BULL_STRONG
    assert env.composite_score >= 70
    assert env.rating == "BULL_STRONG"


def test_all_none():
    dims = {"liquidity": None, "capital": None, "valuation": None,
            "sentiment": None, "fundamentals": None}
    env = compute_environment_score(dims)
    assert env.composite_score == 0.0
    assert env.rating == "BEAR_STRONG"


def test_custom_weights():
    dims = {"liquidity": 90.0, "capital": 10.0}
    weights = {"liquidity": 0.9, "capital": 0.1}
    env = compute_environment_score(dims, weights=weights)
    assert abs(env.composite_score - 82.0) < 0.01
    assert env.rating == "BULL_STRONG"


def test_dimension_details_passthrough():
    dims = {"liquidity": 50.0}
    details = {"liquidity": {"composite": 50.0, "note": "liquidity"}}
    env = compute_environment_score(dims, dimension_details=details)
    assert env.dimension_details["liquidity"]["note"] == "liquidity"


def test_edge_boundaries():
    # boundary between BULL_STRONG and BULL_WEAK
    env = compute_environment_score({"liquidity": 70.0})
    assert env.rating == "BULL_STRONG"
    env = compute_environment_score({"liquidity": 69.9})
    assert env.rating == "BULL_WEAK"
    # boundary between BEAR_WEAK and BEAR_STRONG
    env = compute_environment_score({"liquidity": 30.0})
    assert env.rating == "BEAR_WEAK"
    env = compute_environment_score({"liquidity": 29.9})
    assert env.rating == "BEAR_STRONG"
