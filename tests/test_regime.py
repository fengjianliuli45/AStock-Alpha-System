from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from astock_alpha.data.benchmarks import BenchmarkStore
from astock_alpha.modules.m1_regime.classify import (
    classify_index_raw,
    combine_raw,
    walk_confirmed_regimes,
)
from astock_alpha.modules.m1_regime.regime import RegimeModule
from astock_alpha.modules.m1_regime.sentiment import evaluate_sentiment
from astock_alpha.types import PipelineState, Regime


def _closes_from_returns(start: float, rets: list[float], start_date: date) -> pd.Series:
    vals = [start]
    for r in rets:
        vals.append(vals[-1] * (1 + r))
    idx = [start_date + timedelta(days=i) for i in range(len(vals))]
    return pd.Series(vals, index=idx)


def test_classify_panic_and_bull_bear():
    # long flat then crash
    rets = [0.0] * 70 + [-0.06]
    s = _closes_from_returns(100.0, rets, date(2024, 1, 1))
    assert classify_index_raw(s) == Regime.PANIC

    # gentle uptrend above rising MA
    up = [0.003] * 100
    s_up = _closes_from_returns(100.0, up, date(2024, 1, 1))
    assert classify_index_raw(s_up) in (Regime.BULL, Regime.SIDEWAYS)


def test_combine_and_confirm():
    assert combine_raw(Regime.BEAR, Regime.BULL) == Regime.BEAR
    assert combine_raw(Regime.BULL, Regime.BULL) == Regime.BULL
    assert combine_raw(Regime.PANIC, Regime.BULL) == Regime.PANIC

    raw = [Regime.SIDEWAYS, Regime.BULL, Regime.BULL, Regime.BEAR, Regime.BEAR]
    above = [True] * len(raw)
    conf = walk_confirmed_regimes(raw, above, confirm_days=2)
    assert conf[0] == Regime.SIDEWAYS
    assert conf[1] == Regime.SIDEWAYS  # waiting confirm
    assert conf[2] == Regime.BULL
    assert conf[3] == Regime.BULL
    assert conf[4] == Regime.BEAR


def test_panic_recovery_needs_three_days():
    raw = [Regime.PANIC, Regime.SIDEWAYS, Regime.SIDEWAYS, Regime.SIDEWAYS]
    above = [False, True, True, True]
    conf = walk_confirmed_regimes(raw, above, panic_recover_days=3)
    assert conf[0] == Regime.PANIC
    assert conf[1] == Regime.PANIC
    assert conf[2] == Regime.PANIC
    assert conf[3] == Regime.BEAR


def test_sentiment_gates():
    g = evaluate_sentiment(advance_decline_ratio=0.4)
    assert g.forbid_new_entries
    g2 = evaluate_sentiment(panic_proxy_share=0.2)
    assert g2.cautious_mode


def test_regime_module_with_local_benchmarks(tmp_path):
    # synthesize two bullish series into parquet
    dates = pd.bdate_range("2024-01-02", periods=120)
    close = 100 * np.cumprod(1 + np.full(len(dates), 0.002))
    for name, sym in [("CSI300.parquet", "sh000300"), ("CSI500.parquet", "sh000905")]:
        pd.DataFrame(
            {
                "date": dates,
                "open": close,
                "close": close,
                "high": close,
                "low": close,
                "volume": 1e9,
                "amount": 1e11,
                "symbol": sym,
            }
        ).to_parquet(tmp_path / name, index=False)

    mod = RegimeModule(
        config={
            "regime_multiplier": {"bull": 1.0, "sideways": 0.5, "bear": 0.2, "panic": 0.0},
            "regime": {"ma_window": 60, "confirm_days": 2},
        },
        store=BenchmarkStore(tmp_path),
    )
    assert mod.is_ready()
    state = mod.run(PipelineState(asof=dates[-1].date()))
    assert state.regime in (Regime.BULL, Regime.SIDEWAYS)
    assert state.regime_multiplier > 0
