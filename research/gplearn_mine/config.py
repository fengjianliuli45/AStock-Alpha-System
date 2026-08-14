from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_ROOT = Path(r"D:\下载文件夹\a_share_5y")
DEFAULT_CONSTITUENTS = (
    Path(__file__).resolve().parent / "data" / "csi300_symbols.csv"
)
DEFAULT_ARTIFACTS = REPO_ROOT / "artifacts" / "gplearn_mine"

FEATURE_NAMES = [
    "ret_1",
    "ret_5",
    "ret_20",
    "vol_20",
    "amt_ma_ratio",
    "turn",
    "hl_range",
    "ma_gap_20",
    "v_ma_ratio",
    "ret_from_high_20",
]


@dataclass(frozen=True)
class MineConfig:
    data_root: Path = DEFAULT_DATA_ROOT
    constituents_path: Path | None = DEFAULT_CONSTITUENTS
    artifacts_root: Path = DEFAULT_ARTIFACTS
    years: float = 2.0
    horizon: int = 5
    train_frac: float = 0.7
    purge_horizon: bool = True
    winsor_pct: float = 0.01
    random_state: int = 42
    population_size: int = 500
    generations: int = 15
    tournament_size: int = 20
    # spearman: higher is better; 0.01 would stop almost immediately
    stopping_criteria: float = 0.95
    p_crossover: float = 0.7
    p_subtree_mutation: float = 0.1
    p_hoist_mutation: float = 0.05
    p_point_mutation: float = 0.1
    max_samples: float = 0.8
    parsimony_coefficient: float = 0.001
    init_depth: tuple[int, int] = (2, 4)
    n_jobs: int = 1
    n_quantiles: int = 5
    max_symbols: int | None = None
    disclaimer: str = (
        "本结果仅用于因子挖掘流水线验证，不得作为晋级或实盘依据。"
    )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["data_root"] = str(self.data_root)
        d["constituents_path"] = (
            str(self.constituents_path) if self.constituents_path else None
        )
        d["artifacts_root"] = str(self.artifacts_root)
        d["init_depth"] = list(self.init_depth)
        return d
