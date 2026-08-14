# coding=utf-8
"""Run ~5y local signal backtest on a_share_5y (research matching, not 掘金)."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from astock_alpha.backtest.local_engine import LocalBacktestEngine  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--config",
        type=Path,
        default=ROOT / "configs" / "strategy_v1_0.preregistered.json",
    )
    p.add_argument("--start", default="2021-07-15")
    p.add_argument("--end", default="2026-08-04")
    p.add_argument("--rebalance-every", type=int, default=1, help="1=daily, 5≈weekly")
    p.add_argument("--cash", type=float, default=1_000_000.0)
    p.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / "artifacts" / "local_5y_backtest",
    )
    args = p.parse_args()

    engine = LocalBacktestEngine.from_config_path(args.config)
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    print(
        f"local 5y backtest {start} → {end}, rebalance_every={args.rebalance_every}",
        flush=True,
    )
    t0 = time.time()
    result = engine.run(
        start,
        end,
        initial_cash=args.cash,
        rebalance_every=args.rebalance_every,
    )
    elapsed = time.time() - t0
    args.out_dir.mkdir(parents=True, exist_ok=True)
    nav_path = args.out_dir / "nav.csv"
    summary_path = args.out_dir / "summary.json"
    result.to_csv(nav_path)
    payload = dict(result.summary)
    payload["elapsed_sec"] = elapsed
    summary_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    # last 20 rebalance snapshots
    (args.out_dir / "rebalances_tail.json").write_text(
        json.dumps(result.positions_log[-20:], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"wrote {nav_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
