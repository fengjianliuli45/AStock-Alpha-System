from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from research.gplearn_mine.config import MineConfig
from research.gplearn_mine.constituents import resolve_constituents
from research.gplearn_mine.evaluate import evaluate_split
from research.gplearn_mine.features import build_feature_frame
from research.gplearn_mine.mine import fit_symbolic, predict_factor
from research.gplearn_mine.panel import load_panel, time_split_dates


DISCLAIMER = "本结果仅用于因子挖掘流水线验证，不得作为晋级或实盘依据。"


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="gplearn CSI300 factor mining (research only; not promotion-eligible)"
    )
    p.add_argument("--data-root", type=Path, default=MineConfig.data_root)
    p.add_argument("--constituents", type=Path, default=MineConfig.constituents_path)
    p.add_argument("--artifacts-root", type=Path, default=MineConfig.artifacts_root)
    p.add_argument("--years", type=float, default=2.0)
    p.add_argument("--horizon", type=int, default=5)
    p.add_argument("--train-frac", type=float, default=0.7)
    p.add_argument("--generations", type=int, default=15)
    p.add_argument("--population-size", type=int, default=500)
    p.add_argument("--random-state", type=int, default=42)
    p.add_argument("--max-symbols", type=int, default=None)
    p.add_argument("--no-fetch-constituents", action="store_true")
    p.add_argument("--run-id", type=str, default=None)
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    cfg = MineConfig(
        data_root=args.data_root,
        constituents_path=args.constituents,
        artifacts_root=args.artifacts_root,
        years=args.years,
        horizon=args.horizon,
        train_frac=args.train_frac,
        generations=args.generations,
        population_size=args.population_size,
        random_state=args.random_state,
        max_symbols=args.max_symbols,
    )

    symbols, const_meta = resolve_constituents(
        cfg.constituents_path,
        allow_fetch=not args.no_fetch_constituents,
    )
    if cfg.max_symbols is not None:
        symbols = symbols[: cfg.max_symbols]
        const_meta = {**const_meta, "max_symbols_applied": cfg.max_symbols}

    panel, panel_summary = load_panel(
        cfg.data_root,
        symbols,
        years=cfg.years,
        max_symbols=cfg.max_symbols,
    )
    window_start = pd.Timestamp(panel_summary["window_start"])
    feat = build_feature_frame(
        panel,
        horizon=cfg.horizon,
        window_start=window_start,
        winsor_pct=cfg.winsor_pct,
    )

    purge = cfg.horizon if cfg.purge_horizon else 0
    train_dates, oos_dates, split_meta = time_split_dates(
        feat["date"], train_frac=cfg.train_frac, purge_days=purge
    )
    train = feat[feat["date"].isin(train_dates)].copy()
    oos = feat[feat["date"].isin(oos_dates)].copy()

    model, fit_info = fit_symbolic(train, cfg)
    train = train.copy()
    oos = oos.copy()
    train["factor"] = predict_factor(model, train)
    oos["factor"] = predict_factor(model, oos)

    metrics = {
        "disclaimer": DISCLAIMER,
        "train": evaluate_split(train, n_quantiles=cfg.n_quantiles),
        "oos": evaluate_split(oos, n_quantiles=cfg.n_quantiles),
        "fit": fit_info,
        "split": split_meta,
        "constituents": const_meta,
    }

    run_id = args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = cfg.artifacts_root / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    run_config = {
        "disclaimer": DISCLAIMER,
        "config": cfg.to_dict(),
        "constituents": const_meta,
        "panel": panel_summary,
        "split": split_meta,
    }
    expressions = {
        "disclaimer": DISCLAIMER,
        "best": fit_info["program"],
        "feature_names": list(cfg.to_dict().get("feature_names", [])),
        "metric": fit_info.get("metric"),
        "raw_fitness_train": fit_info.get("raw_fitness"),
        "depth": fit_info.get("depth"),
        "length": fit_info.get("length"),
    }
    # feature names from module constant
    from research.gplearn_mine.config import FEATURE_NAMES

    expressions["feature_names"] = FEATURE_NAMES

    (out_dir / "run_config.json").write_text(
        json.dumps(run_config, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "expressions.json").write_text(
        json.dumps(expressions, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "panel_summary.json").write_text(
        json.dumps(
            {"disclaimer": DISCLAIMER, **panel_summary, "constituents": const_meta},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(DISCLAIMER)
    print(f"run_id={run_id}")
    print(f"out_dir={out_dir}")
    print(f"best={fit_info['program']}")
    print(
        "train_ic={:.4f} oos_ic={:.4f} oos_ls={:.4f}".format(
            metrics["train"]["rank_ic_mean"],
            metrics["oos"]["rank_ic_mean"],
            metrics["oos"]["ls_mean"],
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
