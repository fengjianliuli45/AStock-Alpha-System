# coding=utf-8
"""Wire AStock-Alpha into an existing registered 掘金 strategy (with backup)."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

PROJECTS = Path.home() / ".goldminer3" / "projects"
ROOT = Path(r"D:\AI_Projects\Cursor\Cursor\AStock-Alpha-System")

ENTRY = f'''# coding=utf-8
"""AStock-Alpha 掘金入口 — 在终端对本策略点「运行回测」后查看绩效图。"""

from __future__ import annotations

import os
import sys

ROOT = r"{ROOT.as_posix().replace('/', '\\\\')}"
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

os.environ.setdefault(
    "ASTOCK_ALPHA_CONFIG",
    os.path.join(ROOT, "configs", "strategy_v1_0.gm_backtest_fast.json"),
)

from astock_alpha.gm_host.entry import init, on_bar, on_error  # noqa: E402,F401
'''


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--strategy-id",
        default="5b424e34-80fa-11f1-80f8-a0ad9f23dffe",
        help="Existing registered strategy folder UUID under ~/.goldminer3/projects",
    )
    p.add_argument("--restore", action="store_true", help="Restore main.py.bak_before_astock")
    args = p.parse_args()
    proj = PROJECTS / args.strategy_id
    main_py = proj / "main.py"
    bak = proj / "main.py.bak_before_astock"
    if not proj.exists():
        print("missing project", proj)
        return 1
    if args.restore:
        if not bak.exists():
            print("no backup", bak)
            return 1
        shutil.copy2(bak, main_py)
        print("restored", main_py)
        return 0
    if main_py.exists() and not bak.exists():
        shutil.copy2(main_py, bak)
        print("backed up", bak)
    main_py.write_text(ENTRY, encoding="utf-8")
    print("wired", main_py)
    print("open this strategy in 掘金 -> 运行回测")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
