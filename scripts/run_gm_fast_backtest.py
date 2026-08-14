# coding=utf-8
"""Launch a short Goldminer MODE_BACKTEST so the terminal can show performance charts."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(r"D:\AI_Projects\Cursor\Cursor\AStock-Alpha-System")
SRC = ROOT / "src"
STRATEGY_ID = "5b424e34-80fa-11f1-80f8-a0ad9f23dffe"
TOKEN_PATH = Path.home() / ".myquant" / "token"
MODULE_FILE = SRC / "astock_alpha" / "gm_host" / "terminal_main.py"


def main() -> None:
    # gm.run strips the longest sys.path commonprefix; put src first so import
    # resolves to astock_alpha.gm_host.terminal_main
    src = str(SRC.resolve())
    sys.path = [src] + [p for p in sys.path if p not in ("", src)]
    token = TOKEN_PATH.read_text(encoding="utf-8-sig").strip()
    from gm.api import ADJUST_PREV, MODE_BACKTEST, run  # type: ignore

    # Re-assert after gm import (some SDKs mutate sys.path).
    sys.path = [src] + [p for p in sys.path if p not in ("", src)]
    # gm.api.run compares forward-slash sys.path with filename via commonprefix;
    # backslashes make the shared prefix collapse to "D:" and break import.
    filename = str(MODULE_FILE.resolve()).replace("\\", "/")
    print("sys.path0", sys.path[0], flush=True)
    print("filename", filename, flush=True)

    run(
        strategy_id=STRATEGY_ID,
        filename=filename,
        mode=MODE_BACKTEST,
        token=token,
        backtest_start_time="2024-01-01 09:00:00",
        backtest_end_time="2024-06-30 16:00:00",
        backtest_adjust=ADJUST_PREV,
        backtest_initial_cash=1_000_000,
        backtest_commission_ratio=0.0003,
        backtest_slippage_ratio=0.002,
    )


if __name__ == "__main__":
    main()
