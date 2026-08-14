# coding=utf-8
"""Automate 掘金: create empty Python strategy and wire AStock-Alpha entry."""

from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECTS = Path.home() / ".goldminer3" / "projects"
ENTRY = '''# coding=utf-8
"""AStock-Alpha 掘金入口 — 终端点「运行回测」后看绩效图。"""

from __future__ import annotations

import os
import sys

ROOT = r"D:\\AI_Projects\\Cursor\\Cursor\\AStock-Alpha-System"
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

os.environ.setdefault(
    "ASTOCK_ALPHA_CONFIG",
    os.path.join(ROOT, "configs", "strategy_v1_0.gm_backtest.json"),
)

from astock_alpha.gm_host.entry import init, on_bar, on_error  # noqa: E402,F401
'''


def list_project_ids() -> set[str]:
    if not PROJECTS.exists():
        return set()
    return {p.name for p in PROJECTS.iterdir() if p.is_dir()}


def dump_controls(win, path: Path) -> None:
    lines: list[str] = []
    try:
        for c in win.descendants():
            try:
                ct = c.friendly_class_name()
                tx = (c.window_text() or "").replace("\n", " ")[:80]
                au = ""
                try:
                    au = c.element_info.automation_id or ""
                except Exception:
                    pass
                if tx or au:
                    lines.append(f"{ct}\t{au}\t{tx}")
            except Exception:
                continue
    except Exception as e:
        lines.append(f"ERR {e}")
    path.write_text("\n".join(lines), encoding="utf-8")


def find_goldminer():
    from pywinauto import Desktop

    desk = Desktop(backend="uia")
    for w in desk.windows():
        title = w.window_text() or ""
        if "掘金" in title or "Goldminer" in title or "goldminer" in title.lower():
            return w
    return None


def click_by_text(win, texts: list[str]) -> bool:
    for c in win.descendants():
        try:
            tx = (c.window_text() or "").strip()
        except Exception:
            continue
        if tx in texts:
            try:
                c.click_input()
                return True
            except Exception:
                try:
                    c.invoke()
                    return True
                except Exception:
                    continue
    return False


def main() -> int:
    out = ROOT / "artifacts" / "gm_setup"
    out.mkdir(parents=True, exist_ok=True)

    before = list_project_ids()
    win = find_goldminer()
    if win is None:
        print("GOLDMINER_NOT_FOUND", flush=True)
        return 2

    try:
        win.set_focus()
    except Exception:
        pass
    time.sleep(0.5)
    dump_controls(win, out / "controls_before.txt")

    # Navigate: 量化研究 / 我的策略 / 新建策略
    for step in (
        ["量化研究", "投研"],
        ["我的策略", "策略列表"],
        ["新建策略", "新建"],
    ):
        ok = click_by_text(win, step)
        print(f"CLICK {step} -> {ok}", flush=True)
        time.sleep(0.8)
        dump_controls(win, out / f"controls_after_{step[0]}.txt")

    # Prefer Python + 空策略 in dialog if present
    for label in ["Python", "空策略", "确定", "确认", "完成"]:
        if click_by_text(win, [label]):
            print(f"CLICK {label} -> True", flush=True)
            time.sleep(0.6)

    # Try type strategy name if an edit exists
    try:
        edits = [c for c in win.descendants() if c.friendly_class_name() == "Edit"]
        if edits:
            edits[-1].set_edit_text("AStock-Alpha")
            print("SET_NAME AStock-Alpha", flush=True)
            time.sleep(0.3)
            click_by_text(win, ["确定", "确认", "完成", "创建"])
    except Exception as e:
        print("SET_NAME_FAIL", e, flush=True)

    # Wait for new project folder
    new_id = None
    for _ in range(30):
        time.sleep(1)
        after = list_project_ids()
        created = after - before
        if created:
            new_id = sorted(created)[0]
            break
    if not new_id:
        print("NO_NEW_PROJECT", flush=True)
        dump_controls(win, out / "controls_final.txt")
        return 3

    proj = PROJECTS / new_id
    main_py = proj / "main.py"
    if main_py.exists():
        shutil.copy2(main_py, proj / "main.py.bak_before_astock")
    main_py.write_text(ENTRY, encoding="utf-8")
    print("WIRED", proj, flush=True)
    print("STRATEGY_ID", new_id, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
