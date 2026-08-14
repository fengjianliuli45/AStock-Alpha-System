from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from gplearn.genetic import SymbolicRegressor

from research.gplearn_mine.config import FEATURE_NAMES, MineConfig


def fit_symbolic(
    train: pd.DataFrame,
    cfg: MineConfig,
) -> tuple[SymbolicRegressor, dict[str, Any]]:
    x = train[FEATURE_NAMES].to_numpy(dtype=float)
    y = train["y"].to_numpy(dtype=float)
    # gplearn fitness is greater-is-better for 'pearson' etc; default 'mse' is negative MSE
    model = SymbolicRegressor(
        population_size=cfg.population_size,
        generations=cfg.generations,
        tournament_size=cfg.tournament_size,
        stopping_criteria=cfg.stopping_criteria,
        const_range=(-1.0, 1.0),
        init_depth=cfg.init_depth,
        function_set=("add", "sub", "mul", "div", "abs", "neg", "sqrt", "log"),
        metric="spearman",
        parsimony_coefficient=cfg.parsimony_coefficient,
        p_crossover=cfg.p_crossover,
        p_subtree_mutation=cfg.p_subtree_mutation,
        p_hoist_mutation=cfg.p_hoist_mutation,
        p_point_mutation=cfg.p_point_mutation,
        max_samples=cfg.max_samples,
        feature_names=FEATURE_NAMES,
        verbose=1,
        n_jobs=cfg.n_jobs,
        random_state=cfg.random_state,
    )
    model.fit(x, y)
    info = {
        "program": str(model._program),
        "raw_fitness": float(getattr(model._program, "raw_fitness_", float("nan"))),
        "fitness": float(getattr(model._program, "fitness_", float("nan"))),
        "depth": int(getattr(model._program, "depth_", -1)),
        "length": int(getattr(model._program, "length_", -1)),
        "n_train_rows": int(len(train)),
        "metric": "spearman",
    }
    return model, info


def predict_factor(model: SymbolicRegressor, df: pd.DataFrame) -> pd.Series:
    x = df[FEATURE_NAMES].to_numpy(dtype=float)
    pred = model.predict(x)
    # neutralize non-finite
    pred = np.asarray(pred, dtype=float)
    pred[~np.isfinite(pred)] = np.nan
    return pd.Series(pred, index=df.index, name="factor")
