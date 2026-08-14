# gplearn 小规模因子挖掘设计

> 日期：2026-08-06  
> 状态：已批准；计划见 `docs/superpowers/plans/2026-08-06-gplearn-factor-mine-plan.md`  
> 范围：独立研究流水线 — CSI300 × 近 2 年日度价量 → 符号回归挖因子 → train/OOS 评估  
> 关联：桌面《量化策略完整模块设计_v1.0》；教训 L-001 / L-002  
> 借鉴边界：不接入 m4–m10；不晋级；不做完整组合回测

---

## 1. 目标与边界

### 1.1 目标

在 AStock-Alpha 仓库内增加**独立研究工具**，用 `gplearn.SymbolicRegressor` 从日度价量特征中挖掘可读因子表达式，并以时间切分的 OOS Rank IC / 分层收益做粗评估，验证流水线可跑通。

### 1.2 已定决策

| 项 | 选择 |
|---|---|
| 落点 | 独立工具：`research/gplearn_mine/`（不改 pipeline / m4 stub） |
| 数据源 | 本机 `a_share_5y/qfq`（默认 `D:\下载文件夹\a_share_5y`） |
| 样本 | 沪深300 成分 × 近 2 年日线 |
| 标签 | 未来 5 日简单收益：`close[t+5]/close[t] - 1` |
| 评估 | 时间切分 train/OOS；Rank IC + 简化分层多空 |
| 产出 | 表达式、metrics、样本摘要；标明不可晋级 |

### 1.3 做 / 不做

| 做 | 不做（本轮） |
|---|---|
| 面板加载 + CSI300 过滤 + 特征/标签构造 | 接入 StrategyPipeline / m4–m5 |
| SymbolicRegressor 小规模搜索 | 参数网格扫爆 / 多标签并行 |
| train-only 拟合；OOS 只评估 | 完整成本/冲击/阻塞回测（L-006/L-007） |
| 表达式与 metrics 落盘 | 行业中性 / PIT 基本面（L-002 已知缺口） |
| 最小 README + 可复现 CLI | 实盘/仿真、晋级门自动通过 |

### 1.4 成功标准

1. 一条 CLI 可在本机跑通（含依赖安装说明）。  
2. 产出目录含：`expressions.json`、`metrics.json`、`run_config.json`。  
3. OOS Rank IC 与分层收益可复现（固定 random_state）。  
4. 文档与产物均标明：**研究探索，不可晋级**。  
5. 不修改现有 `src/astock_alpha` 业务模块（除可选极薄共用工具外，优先自包含）。

---

## 2. 目录与入口

```text
research/gplearn_mine/
  README.md
  __init__.py
  config.py          # 默认路径与超参
  panel.py           # 读 qfq、筛成分、切窗口
  features.py        # 特征与标签（无未来信息）
  mine.py            # gplearn 拟合
  evaluate.py        # Rank IC / 分层
  run.py             # CLI
artifacts/gplearn_mine/<run_id>/
  run_config.json
  expressions.json
  metrics.json
  panel_summary.json
```

CLI 示例：

```powershell
python -m research.gplearn_mine.run --years 2 --horizon 5
```

---

## 3. 数据

### 3.1 价量

- 根目录：`--data-root`，默认 `D:\下载文件夹\a_share_5y`  
- 文件：`qfq/{SHSE|SZSE}.xxxxxx.parquet`  
- 必要列：`date, symbol, open, high, low, close, volume, amount`（`turn` 有则用）  
- 窗口：`end = max(date)`，`start = end - years`（默认 2）

### 3.2 成分

优先级：

1. `--constituents` 指向本地 CSV/Parquet（列 `symbol`）  
2. 若存在 `data/benchmarks` 旁或配置中的成分快照则用  
3. 否则尝试掘金 `stk_get_index_constituents`（失败则报错并提示导出方式）

首版允许「静态近期成分」近似（非严格历史 PIT 成分）；在 `run_config` 中记录来源与日期。**文档声明：成分非逐日 PIT，OOS 解读须打折。**

### 3.3 标签

\[
y_{i,t} = \frac{close_{i,t+5}}{close_{i,t}} - 1
\]

- 末 `horizon` 个交易日无标签，丢弃  
- 停牌/缺失 close 的样本丢弃  
- 不使用开盘价成交假设以外的复杂执行模型（本轮只挖因子）

---

## 4. 特征（终端输入）

全部在 \(t\) 及以前可计算；截面内可选 z-score / rank（默认截面 rank 到 \([0,1]\)，降低量纲）。

| 名称 | 定义（示意） |
|---|---|
| `ret_1` | \(close_t/close_{t-1}-1\) |
| `ret_5` | \(close_t/close_{t-5}-1\) |
| `ret_20` | \(close_t/close_{t-20}-1\) |
| `vol_20` | 近 20 日 `ret_1` 标准差 |
| `amt_ma_ratio` | \(amount_t / MA(amount,20)\) |
| `turn` | 换手（缺失则用 volume 代理并标记） |
| `hl_range` | \((high-low)/close\) |
| `ma_gap_20` | \(close/MA(close,20)-1\) |
| `v_ma_ratio` | \(volume_t / MA(volume,20)\) |
| `ret_from_high_20` | \(close / max(high,20) - 1\) |

禁止：任何依赖 \(t+k\) 的字段；禁止把标签或其变换混入特征。

---

## 5. 模型与切分

### 5.1 时间切分

- 按交易日排序，前 **70%** 日期 → train，后 **30%** → OOS  
- 仅在 train 上 `fit`；OOS 只 `predict` / 评估  
- 可选 purge：train 末日与 OOS 首日之间空出 `horizon` 个交易日，降低标签重叠泄漏

### 5.2 gplearn 超参（首版默认，冻结进 run_config）

| 参数 | 默认 | 说明 |
|---|---|---|
| `population_size` | 500 | 小规模 |
| `generations` | 15 | 短代数 |
| `tournament_size` | 20 | |
| `stopping_criteria` | 0.95 | spearman 越高越好；过低会秒停 |
| `p_crossover` | 0.7 | |
| `p_subtree_mutation` | 0.1 | |
| `p_hoist_mutation` | 0.05 | |
| `p_point_mutation` | 0.1 | |
| `max_samples` | 0.8 | |
| `parsimony_coefficient` | 0.001 | 控制复杂度 |
| `init_depth` | (2, 4) | 浅树 |
| `random_state` | 42 | 可复现 |
| `n_jobs` | 1 | 首版单进程，避免环境坑 |
| `feature_names` | 上表 | 表达式可读 |

函数集：`add, sub, mul, div, abs, neg, sqrt, log`（保护除零用 gplearn 默认 protected）。

样本行：train 期内「股票×日」展开；可对极端标签做 winsorize（1%/99%）并写入 config。

### 5.3 多表达式

拟合结束后导出：

- 最优个体表达式  
- 可选：最后一代 fitness 前 K=5 的去重表达式（若 API 易取；否则仅最优）

---

## 6. 评估

在 train 与 OOS 上分别计算（不得用 OOS 选模）：

1. **Rank IC**：每日截面 Spearman(factor, y)，再对日序列取均值 / 标准差 / IR(=mean/std)  
2. **分层**：每日按因子分 5 组，多空 = 顶组标签均值 − 底组标签均值；报告日均多空  
3. **覆盖率**：有效截面股票数均值  

失败不伪装：若 OOS IC≈0 或为负，照实写入 metrics，不自动加代/拧参（L-001）。

---

## 7. 依赖与环境

- Python 3.11+ 优先；本机若为 3.14，需验证 `gplearn` / `scikit-learn` 可装  
- `requirements-research.txt` 或 README 列出：`gplearn`, `scikit-learn`, `pandas`, `numpy`, `pyarrow`  
- 与业务 `pyproject` 解耦，避免污染主依赖

---

## 8. 风险与声明

| 风险 | 应对 |
|---|---|
| 过拟合（L-001） | 小搜索空间、固定超参、OOS 只评估、禁止边看边拧 |
| 纯量价（L-002） | 文档标明局限；不声称可晋级 |
| 成分非 PIT | run_config 记录；解读打折 |
| 标签重叠 | purge `horizon` 日 |
| 结果≠可交易（L-006/L-007） | 不做撮合回测；不报年化净值冒充策略绩效 |

产物页眉/README 固定句：

> 本结果仅用于因子挖掘流水线验证，不得作为晋级或实盘依据。

---

## 9. 验收清单

- [ ] `python -m research.gplearn_mine.run` 退出码 0  
- [ ] `artifacts/gplearn_mine/<run_id>/` 三份核心 JSON 齐全  
- [ ] `metrics.json` 含 train/OOS 的 Rank IC 与分层多空  
- [ ] `expressions.json` 含可读公式字符串  
- [ ] README 含数据路径、依赖、不可晋级声明  

---

## 10. 后续（非本轮）

- 严格历史成分 PIT  
- 行业中性 / 基本面终端  
- 表达式接入 m4/m5 打分  
- 信号级薄回测（仍不可直接晋级）
