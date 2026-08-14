# gplearn 小规模因子挖掘（研究用）

> **本结果仅用于因子挖掘流水线验证，不得作为晋级或实盘依据。**

依据：`docs/superpowers/specs/2026-08-06-gplearn-factor-mine-design.md`

## 依赖

```powershell
pip install -r requirements-research.txt
```

## 数据

- 默认价量根目录：`D:\下载文件夹\a_share_5y\qfq`
- 成分：`research/gplearn_mine/data/csi300_symbols.csv`（缺失时优先 baostock HS300，其次东财/可选掘金；**非逐日 PIT**）

## 运行

在仓库根目录：

```powershell
python -m research.gplearn_mine.run
```

常用参数：

```powershell
python -m research.gplearn_mine.run --years 2 --horizon 5
python -m research.gplearn_mine.run --max-symbols 80 --generations 5 --run-id smoke
```

产物：`artifacts/gplearn_mine/<run_id>/`

- `expressions.json` — 因子表达式
- `metrics.json` — train / OOS Rank IC 与分层多空
- `run_config.json` — 冻结超参与数据来源

## 局限（必读）

- 纯量价，无 PIT 基本面（L-002）
- 成分静态快照，非历史 PIT
- 不做成本/阻塞/撮合回测（L-006 / L-007）
- 禁止边看 OOS 边拧参（L-001）
