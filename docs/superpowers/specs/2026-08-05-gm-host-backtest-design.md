# 掘金宿主回测接入设计

> 日期：2026-08-05  
> 状态：已批准并实现中；计划见 `docs/superpowers/plans/2026-08-05-gm-host-backtest-plan.md`  
> 范围：方案 1 — 掘金宿主 + 本库 StrategyPipeline + 信号级薄适配；仅回测  
> 关联：桌面《量化策略完整模块设计_v1.0》；现有 `SnapshotProvider` / m0–m3  
> 借鉴边界：符号与生命周期对齐掘金 gm SDK；决策逻辑不迁出本库；不做完整 m6–m8

---

## 1. 目标与边界

### 1.1 目标

把 `AStock-Alpha-System` 策略决策接进掘金终端：在 `MODE_BACKTEST` 下按日运行现有 `StrategyPipeline`，用信号级组合适配生成目标权重，经掘金 `order_target_percent` 撮合，使终端产出净值/回撤等绩效图。

### 1.2 已定决策

| 项 | 选择 |
|---|---|
| 运行形态 | 掘金宿主（`init` / `on_bar`），内部调用本库 pipeline |
| 首版范围 | 仅回测（不做仿真/实盘） |
| 下单逻辑 | 信号级薄适配（非完整 m6–m8） |
| 持仓构建 | `universe` → `avg_amount_20d` Top-N 等权 |
| N / 现金 | 复用 `portfolio.max_holdings`、`cash_floor` |
| 仓位缩放 | 再乘 `regime_multiplier`（panic → 空仓） |
| 数据 | `data.provider` 双源可切换，默认 `gm`；保留 `a_share_5y` |

### 1.3 做 / 不做

| 做 | 不做（本轮） |
|---|---|
| `GmSnapshotProvider` + provider 工厂分支 | 仿真 / 实盘下单 |
| `GmBenchmarkStore`（m1 指数，gm 模式） | 完整 m6 入场 / m7 仓位 / m8 出场业务 |
| `SignalPortfolioAdapter` | 本库自建撮合引擎与画图 |
| 掘金宿主入口与日频再平衡 | 晋级门 metrics 自动从掘金回灌 |
| optional `gm` 依赖；CLI `run-once` 不破坏 | 改治理参数哈希语义 |

### 1.4 成功标准

1. 掘金终端可加载策略并完成一段（建议 ≥1 年）日频回测，终端展示净值/回撤等报告图。  
2. `provider=gm` 与 `provider=a_share_5y` 均可装配；文档/示例如默认 `gm`。  
3. 持仓数 ≤ `max_holdings`；panic 日目标接近空仓。  
4. 单测覆盖：adapter 排序/等权/`cash_floor`/`regime_multiplier`；工厂识别 `gm`。  
5. CLI `run-once` + 本地源路径仍可用。

---

## 2. 总架构

```
掘金终端 MODE_BACKTEST
    │
    ├─ init(context)
    │     加载 strategy JSON → 装配 StrategyPipeline
    │     按 data.provider 选择 SnapshotProvider / Benchmark
    │
    └─ on_bar(context, bars)   # 日频再平衡
          asof ← 回测当前日
          state ← StrategyPipeline.run(asof)   # m0→m10
          targets ← SignalPortfolioAdapter(state)
          order_target_percent(...)            # 掘金撮合 → 终端绩效图
```

**边界**

- **本库**：决策（治理 / Regime / 股票池）+ 信号→权重适配 + 数据 Provider 抽象。  
- **掘金**：生命周期、行情（`provider=gm` 时）、撮合与绩效报告。  
- **类型复用**：适配器产出已有 `TargetPosition`；不新增平行持仓模型。

---

## 3. 组件与目录

| 路径（拟定） | 职责 |
|---|---|
| `src/astock_alpha/gm_host/entry.py` | 掘金 `init` / `on_bar` / `on_error` 入口 |
| `src/astock_alpha/gm_host/runtime.py` | 配置加载、pipeline 装配、再平衡编排 |
| `src/astock_alpha/data/gm_provider.py` | `GmSnapshotProvider` |
| `src/astock_alpha/data/gm_benchmarks.py` | `GmBenchmarkStore` |
| `src/astock_alpha/data/providers.py` | 扩展 `build_snapshot_provider` 支持 `"gm"` |
| `src/astock_alpha/portfolio/signal_adapter.py` | `SignalPortfolioAdapter` |
| `configs/strategy_v1_0.gm_backtest.json`（或同名示例） | 默认 `provider=gm` + `gm_host` 段 |
| `pyproject.toml` | optional-dependencies：`gm` |

策略在掘金终端中指向宿主入口模块；本库以可安装包形式被该进程 import。

---

## 4. 数据层与配置

### 4.1 Provider

| `data.provider` | Snapshot | Benchmark（m1） |
|---|---|---|
| `gm`（默认，掘金回测） | `GmSnapshotProvider` | `GmBenchmarkStore`（CSI300/CSI500） |
| `a_share_5y` | 现有 `AShare5ySnapshotProvider` | 现有本地 `benchmarks_root` |

**`GmSnapshotProvider`**

- 实现 `SnapshotProvider.load(asof, symbols=None) -> list[StockSnapshot]`。  
- 使用 gm 历史/标的接口拼 PIT 字段；符号保持 `SHSE.*` / `SZSE.*` / `BJSE.*`。  
- `history` 单次约 33000 条限制：分批请求 + 按 asof 日缓存。  
- 能提供的硬过滤字段优先填齐（ST/停牌/上市天数/流动性等）；缺失字段保持 `None`，遵循 m3「不误杀」。  
- 总市值：gm 有则用；否则可挂现有 `MarketCapEnrichingProvider`（Tushare）。

**依赖**

- `gm` 为 optional；未安装且 `provider=gm` 时启动失败并提示；`a_share_5y` 不依赖 gm。

### 4.2 配置增量

```json
"data": {
  "provider": "gm",
  "gm_token_path": null,
  "gm_adjust": "prev",
  "max_symbols": null,
  "a_share_5y_root": "...",
  "benchmarks_root": "...",
  "enrich_market_cap": true
},
"gm_host": {
  "frequency": "1d",
  "rebalance": "daily",
  "backtest_start": "2021-01-01",
  "backtest_end": "2025-12-31",
  "initial_cash": 1000000
}
```

Token：优先终端已登录上下文；否则读 `gm_token_path` 或约定环境变量。  
仓位参数继续使用现有 `portfolio` / `regime_multiplier` / `costs`（costs 首版仅作与掘金回测设置对齐的说明，不在本库重算成交）。

---

## 5. 信号适配与下单映射

### 5.1 `SignalPortfolioAdapter`

**输入**：`PipelineState` + 当日 `amount_by_symbol: dict[str, float | None]`（由 runtime 在 `provider.load` 之后从 `StockSnapshot.avg_amount_20d` 构建并传入）。  
**输出**：`list[TargetPosition]`，并写回 `state.targets`。

**规则**

1. 标的池 = `state.universe`（不用可能为空的 `candidates`）。  
2. 按 `avg_amount_20d` 降序取 Top-N，`N = portfolio.max_holdings`。  
3. 可投资金权重 `W = (1 - cash_floor) * regime_multiplier`；`panic` 时 multiplier 为 0 → 空仓。  
4. Top-N 内等权：每只 `weight = W / k`（`k` 为实际入选只数；`k=0` 则空仓）。  
5. 缺 `avg_amount_20d` 的标的排在有值之后；不足 N 则有多少用多少。  
6. `reason` 标注来源（如 `signal:avg_amount_20d_topn`），便于日志。

### 5.2 掘金映射

- 每个再平衡日：对目标集合调用 `order_target_percent(symbol, weight)`。  
- 昨日有仓且今日不在目标：`order_target_percent(symbol, 0)`。  
- 不手写股数；滑点/佣金/印花税使用掘金回测账户设置。

### 5.3 明确不做

- 涨跌停买入拦截、止损/时间出场等完整 m6/m8（首版用每日信号调仓近似）。  
- 回测路径不启用实盘 `trading_enabled` 门；不向实盘发单。

---

## 6. 宿主回调与错误处理

### 6.1 回调

| 回调 | 行为 |
|---|---|
| `init` | 加载配置、装配 pipeline/provider、记录回测参数；订阅策略所需日频基准（及权限允许范围内的标的策略） |
| `on_bar` | 仅日线触发：取 asof → `pipeline.run` → adapter → 调仓 |
| `on_error` | 记录错误；不静默忽略；致命配置/连接错误中止 |

### 6.2 错误与降级

| 情况 | 行为 |
|---|---|
| token / 终端未连接 | `init` 失败，明确报错 |
| 快照字段部分缺失 | m3 规则：incomplete 不误杀 |
| `universe` 为空 | 目标空仓（清旧仓） |
| `provider=gm` 但未装 SDK | 启动失败并提示 |
| 单日 pipeline 异常 | 当日跳过下单并告警；默认不因单日失败中止整段回测 |

### 6.3 订阅说明

- 免费版**实盘**实时订阅常限约 50 标的；**回测**订阅限制以终端权限为准，实现时避免把实盘 50 限误用到回测路径。  
- 交易以 `order_target_percent` 为主，不要求实盘式全市场实时订阅。

---

## 7. 测试与验收

### 7.1 单测（本库）

- `SignalPortfolioAdapter`：排序、Top-N、等权、`cash_floor`、`regime_multiplier=0`、缺失成交额、空 universe。  
- `build_snapshot_provider`：识别 `"gm"`（可用 fake/stub 避免强依赖终端）。  
- 现有 universe/regime/governance/CLI 冒烟不回归。

### 7.2 手工验收（掘金终端）

1. 加载宿主策略，`provider=gm`，跑 ≥1 年日频回测。  
2. 终端出现绩效图与成交/持仓明细。  
3. 抽查若干再平衡日：持仓数 ≤ N；panic 窗口接近空仓。  
4. 切换 `provider=a_share_5y` 的 CLI `run-once` 仍成功（不要求同一段在掘金内用本地源完整复现）。

---

## 8. 实现顺序（供后续 plan）

1. `SignalPortfolioAdapter` + 单测  
2. provider 工厂 `"gm"` 分支 + `GmSnapshotProvider` / `GmBenchmarkStore`（可先 stub 接口再接真 API）  
3. `gm_host` runtime + entry  
4. 示例配置与 README 掘金回测说明  
5. 终端手工回测验收  

---

## 9. 非目标与后续

- 仿真/实盘：`GmExecutionBroker` + `trading_enabled` / 晋级门联动。  
- 正式 m6/m7/m8 替换信号薄适配。  
- 掘金绩效导出 → `PromotionMetrics` 自动评估。  
- 财务/解禁等 incomplete 字段的 gm/Tushare enrich 加深。
