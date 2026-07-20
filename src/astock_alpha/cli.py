from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from astock_alpha.pipeline import StrategyPipeline


def _default_config() -> Path:
    return Path(__file__).resolve().parents[2] / "configs" / "strategy_v1_0.preregistered.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AStock Alpha modular strategy CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run-once", help="Run one dry pipeline pass")
    p_run.add_argument("--config", type=Path, default=_default_config())
    p_run.add_argument("--asof", type=str, default=None, help="YYYY-MM-DD")

    p_ready = sub.add_parser("readiness", help="Show which modules are implemented")
    p_ready.add_argument("--config", type=Path, default=_default_config())

    p_gate = sub.add_parser("show-governance", help="Print frozen hash and trading switch")
    p_gate.add_argument("--config", type=Path, default=_default_config())

    args = parser.parse_args(argv)
    pipe = StrategyPipeline.from_config_path(args.config)

    if args.cmd == "readiness":
        print(json.dumps(pipe.readiness(), indent=2, ensure_ascii=False))
        return 0

    if args.cmd == "show-governance":
        g = pipe.governance
        assert g is not None
        print(
            json.dumps(
                {
                    "strategy_name": g.strategy_name,
                    "version": g.version,
                    "status": g.status.value,
                    "trading_enabled": g.trading_enabled,
                    "parameter_hash": g.parameter_hash,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    if args.cmd == "run-once":
        asof = date.fromisoformat(args.asof) if args.asof else date.today()
        state = pipe.run(asof)
        print(json.dumps(pipe.summary(state), indent=2, ensure_ascii=False))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
