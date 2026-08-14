# coding=utf-8
"""Run ~5y Goldminer MODE_BACKTEST for ai克隆策略 (local a_share_5y + GM matching)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(r"D:\AI_Projects\Cursor\Cursor\AStock-Alpha-System")
SRC = ROOT / "src"
STRATEGY_ID = "2eb880ad-93e2-11f1-9d91-a0ad9f23dffe"
TOKEN_PATH = Path.home() / ".myquant" / "token"
MODULE_FILE = SRC / "astock_alpha" / "gm_host" / "terminal_main.py"
CONFIG = ROOT / "configs" / "strategy_v1_0.gm_backtest_5y.json"


def main() -> None:
    os.environ["ASTOCK_ALPHA_CONFIG"] = str(CONFIG)
    src = str(SRC.resolve())
    sys.path = [src] + [p for p in sys.path if p not in ("", src)]
    token = TOKEN_PATH.read_text(encoding="utf-8-sig").strip()
    from gm.api import ADJUST_PREV, MODE_BACKTEST, run  # type: ignore

    sys.path = [src] + [p for p in sys.path if p not in ("", src)]
    filename = str(MODULE_FILE.resolve()).replace("\\", "/")
    print("config", CONFIG, flush=True)
    print("strategy_id", STRATEGY_ID, flush=True)
    print("filename", filename, flush=True)

    run(
        strategy_id=STRATEGY_ID,
        filename=filename,
        mode=MODE_BACKTEST,
        token=token,
        backtest_start_time="2021-07-20 09:00:00",
        backtest_end_time="2026-08-04 16:00:00",
        backtest_adjust=ADJUST_PREV,
        backtest_initial_cash=1_000_000,
        backtest_commission_ratio=0.0003,
        backtest_slippage_ratio=0.002,
    )


if __name__ == "__main__":
    main()
