# 实现计划：掘金宿主回测接入

依据：`docs/superpowers/specs/2026-08-05-gm-host-backtest-design.md`

教训约束（动手前已扫）：L-001 不拧参复活；L-005 Regime 缩放必须生效；L-006/L-007 信号等权+乐观成本仅作链路验证，文档标明不可当可晋升结果；本轮不做完整出场（知悉 L-003 缺口，属设计非目标）。

---

## 任务

### 1. `SignalPortfolioAdapter` + 单测

- 新增 `src/astock_alpha/portfolio/__init__.py`
- 新增 `src/astock_alpha/portfolio/signal_adapter.py`
  - `build_signal_targets(state, amount_by_symbol, max_holdings, cash_floor) -> list[TargetPosition]`
  - 规则严格按规格 §5.1（Top-N `avg_amount_20d`、等权、`W=(1-cash_floor)*regime_multiplier`）
  - 写回 `state.targets`
- 新增 `tests/test_signal_adapter.py`：排序、Top-N、等权、`cash_floor`、multiplier=0、缺失成交额、空 universe

**验收**：`pytest tests/test_signal_adapter.py -q` 通过

### 2. Provider 工厂 `"gm"` + Gm 数据适配

- 扩展 `src/astock_alpha/data/providers.py`
  - `provider == "gm"` → 构造 `GmSnapshotProvider`（可选再包 `MarketCapEnrichingProvider`）
  - 未安装 `gm` 且选 gm → 抛清晰 `ImportError`/`RuntimeError`
- 新增 `src/astock_alpha/data/gm_provider.py`：`GmSnapshotProvider`
  - `load(asof, symbols=None)` → `list[StockSnapshot]`
  - history 分批（≤33000）、按日缓存；复权读 `data.gm_adjust`
  - 填齐可得硬过滤字段；其余 `None`
- 新增 `src/astock_alpha/data/gm_benchmarks.py`：`GmBenchmarkStore`
  - 接口对齐现有 `BenchmarkStore`  consumable 方式（供 m1 取 CSI300/CSI500）
- 改 `src/astock_alpha/modules/registry.py`
  - `data.provider == "gm"` 时用 `GmBenchmarkStore`，否则沿用本地 `benchmarks_root`
- `pyproject.toml`：`[project.optional-dependencies] gm = ["gm"]`（版本按环境可装为准）
- 单测：`tests/test_gm_provider_factory.py` 用 stub/monkeypatch，不连真终端

**验收**：工厂识别 gm；无 SDK 时报错信息可读；本地 `a_share_5y` 路径回归通过

### 3. `gm_host` runtime + entry

- 新增 `src/astock_alpha/gm_host/__init__.py`
- 新增 `src/astock_alpha/gm_host/runtime.py`
  - 加载 JSON 配置 → `StrategyPipeline`
  - 每日：`pipeline.run(asof)` → 从当日快照建 `amount_by_symbol` → adapter → 目标权重 dict
  - 单日异常：告警并跳过下单（规格 §6.2）
- 新增 `src/astock_alpha/gm_host/entry.py`
  - `init` / `on_bar` / `on_error`（掘金回调签名）
  - 调仓：`order_target_percent`；不在目标内的旧仓归零
  - 回测参数：`gm_host.backtest_*` / `initial_cash` / `frequency=1d`
- 可选薄封装 `gm_host/orders.py`：目标权重 → 下单，便于单测 mock

**验收**：无终端时可用 mock 测「目标权重 → 调用顺序」；有终端时能 import 入口

### 4. 示例配置与文档

- 新增 `configs/strategy_v1_0.gm_backtest.json`
  - 基于现有预注册配置，`data.provider=gm`，补 `gm_host` 段
  - `max_holdings` / `cash_floor` 保持可改；注释或 README 说明当前预注册 N=3
- 更新 `README.md`：掘金回测步骤（安装 `[gm]`、终端 token、指向 entry、跑回测看绩效图）
- 规格状态改为「已批准，实现中」

**验收**：文档步骤可跟；配置可被 runtime 加载

### 5. 回归 + 终端手工验收

- `python -m pytest -q` 全绿
- CLI：`python -m astock_alpha.cli run-once --config configs/strategy_v1_0.preregistered.json`（本地源）不破坏
- 掘金终端：加载宿主，`provider=gm`，≥1 年日频回测 → 净值/回撤图；抽查持仓 ≤ N、panic 近空仓

**验收**：规格 §1.4 / §7 全部满足

---

## 实现顺序

1 → 2 → 3 → 4 → 5（不可并行颠倒：adapter 无依赖；host 依赖 provider+adapter）

## 明确不做（本 plan）

仿真/实盘、完整 m6–m8、本库画图、晋级门自动灌 metrics、财务/解禁 enrich 加深
