# coding=utf-8
"""掘金终端可直接加载的策略薄封装。

用法：
1. pip install -e ".[gm]"（仓库根目录）
2. 终端登录，配置 token（或 configs 里 data.gm_token_path / 环境变量 GM_TOKEN）
3. 用本文件作为策略入口，或：
   python strategies/gm_astock_alpha.py

可选环境变量：
  ASTOCK_ALPHA_CONFIG  指向 strategy JSON
  GM_TOKEN             掘金 token
  GM_STRATEGY_ID       策略 ID
"""

from __future__ import annotations

import os
from pathlib import Path

from astock_alpha.gm_host.entry import init, on_bar, on_error, run_backtest

__all__ = ["init", "on_bar", "on_error"]


if __name__ == "__main__":
    here = Path(__file__).resolve()
    run_backtest(
        filename=str(here),
        strategy_id=os.environ.get("GM_STRATEGY_ID"),
        token=os.environ.get("GM_TOKEN"),
        config_path=os.environ.get("ASTOCK_ALPHA_CONFIG"),
    )
