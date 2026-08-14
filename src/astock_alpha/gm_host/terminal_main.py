# coding=utf-8
"""Importable strategy module for gm.api.run(filename=...)."""

from __future__ import annotations

import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
# Prefer ASTOCK_ALPHA_CONFIG from env (set by run scripts / project main.py).
_CFG = Path(os.environ.get("ASTOCK_ALPHA_CONFIG") or (_ROOT / "configs" / "strategy_v1_0.gm_backtest_5y.json"))
os.environ.setdefault("ASTOCK_ALPHA_CONFIG", str(_CFG))

from astock_alpha.gm_host.entry import init, on_bar, on_error  # noqa: E402,F401
