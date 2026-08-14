# 模块三（股票池）安检对齐查漏补缺设计

> 日期：2026-07-19  
> 状态：已批准并实现（2026-07-19）  
> 范围：方案 2 — 规格 + 过滤逻辑/契约对齐；不接真实数据源  
> 关联：桌面《量化策略完整模块设计_v1.0》模块 3；教训库 L-001 相关治理纪律  
> 借鉴边界：仅吸收「安检共识」（ST/停牌/次新/流动性/市值/PIT）；不吸收选股因子；不做研究池/交易池分层

---

## 1. 目标与边界

### 1.1 目标

把学术论文、聚宽等论坛、GitHub 实务中成熟的 **股票池安检共识** 钉进模块三的规格与代码契约，使过滤行为与设计文档一致，并用测试防止回归。

### 1.2 做 / 不做

| 做 | 不做（本轮） |
|---|---|
| 明确每条安检的字段、踢出条件、缺失处理 | 不接真实行情/财务数据源 |
| 强制按决策日 PIT；按日 ST，禁止用当前简称回刷历史 | 不做研究池 vs 交易池两层 |
| 涨跌停退出股票池硬踢，归属模块六说明 | 不加 ROE/均线/涨停次数等选股因子 |
| 补契约字段、配置开关、单测 | 不改模块 0 持久化（另开轮次） |

### 1.3 成功标准

1. 规格中每条安检均有「与共识对照」说明。  
2. 代码契约字段齐全；缺失行为符合「宁可不踢、不误杀」。  
3. 单测覆盖：按日 ST、停牌、次新、流动性、市值、财务 PIT 缺失、涨跌停不进股票池硬踢。

---

## 2. 安检清单与字段契约

### 2.1 硬安检（AND）

| 安检项 | 字段（asof 已知） | 踢出条件 | 缺失时 | 共识对照 |
|---|---|---|---|---|
| ST / 退市风险 | `is_st`, `is_delist_risk`（按日布尔优先；名称仅兜底） | 任一为真 | incomplete，不踢 | 论文 / 聚宽 / aurumq |
| 停牌 | `is_suspended`（新增） | 为真 | incomplete，不踢 | 论坛 / aurumq / zer0share |
| 次新 | `listed_trading_days` | `< 120` | incomplete，不踢 | 论文常 6 个月；本设计更严 |
| 流动性 | `avg_amount_20d` | `< 1e8`（1 亿） | incomplete，不踢 | 实务主流 |
| 市值 | `total_market_cap` | `< 5e9`（50 亿） | incomplete，不踢 | 实务绝对门槛；学术分位本轮不采用 |
| 解禁 | `unlock_pct_next_30d` | `> 0.05` | incomplete，不踢 | 实战常用 |
| 减持 | `ctrl_shareholder_reduce_60d` | 为真 | incomplete，不踢 | 实战常用 |
| 业绩暴雷 | `worst_quarter_ni_yoy_180d` + `fundamentals_asof` | `<= -0.50` | incomplete，不踢 | 设计文档；须 PIT |
| 商誉 | `goodwill_to_equity` + `fundamentals_asof` | `> 0.30` | incomplete，不踢 | 设计文档；须 PIT |

### 2.2 涨跌停（归属变更）

- 字段 `buy_blocked_limit_up` **保留**在快照中，供模块六入场阻塞使用。  
- 模块三默认 **不** 因涨跌停硬踢（配置 `limit_up_in_universe: false`）。  
- 理由：论坛「三停」属于下单日可成交性，不是「值不值得进研究池」。

### 2.3 软过滤（可关）

在 `apply_soft_filters: true` 时：

| 项 | 字段 | 有数据且触发 | 缺失 |
|---|---|---|---|
| 质押 | `pledge_ratio` | `> 0.50` → 踢 | incomplete |
| 造假/违规 5 年 | `has_fraud_or_violation_5y` | 真 → 踢 | incomplete |
| 非标审计 | `non_standard_audit` | 真 → 踢 | incomplete |
| 分析师覆盖 | `analyst_coverage` | **不踢**；过低仅标 `analyst_coverage_low` | incomplete |

### 2.4 PIT 与 ST 硬规则

1. 所有字段语义 = 在 `asof` 当天已知；禁止用最新状态回填历史。  
2. ST：必须按日 `is_st`；禁止「当前简称含 ST 则删除该股全部历史」。名称匹配仅在当日布尔缺失时兜底。  
3. 财务类：若无有效 `fundamentals_asof` 或 `fundamentals_asof > asof`，则暴雷/商誉视为缺失（incomplete），不踢。  
4. `StockSnapshot` 新增：`is_suspended: bool | None`、`fundamentals_asof: date | None`。

---

## 3. 流程、降级、配置、测试

### 3.1 运行流程

```
SnapshotProvider.load(asof, symbols?)
  → 逐票 evaluate_stock（硬 AND + 可选软过滤）
  → PipelineState.universe / reject_counts / incomplete_filters / details
```

### 3.2 降级

- 字段缺失 → 该条不踢，记 incomplete，warning。  
- 本轮不设「incomplete 比例过高则空仓」熔断。  
- 无 Provider → universe 空 + 明确告警（保持现状）。  
- Provider 抛错 → universe 空，错误进入 meta/warnings，不得假装全通过。  
- 单票字段类型非法 → 当缺失，不中断整池。

### 3.3 配置（预注册 JSON `universe` 段）

保留既有阈值键；新增：

| 键 | 默认 | 含义 |
|---|---|---|
| `enforce_suspension` | `true` | 启用停牌硬安检 |
| `limit_up_in_universe` | `false` | 是否在股票池因涨停硬踢 |

改阈值或开关 = 新策略版本号（模块 0 纪律）。

### 3.4 测试清单

1. 按日 ST：历史非 ST、今日 ST → 仅今日被踢。  
2. `is_suspended=True` → 踢；`None` → 不踢 + incomplete。  
3. 次新 / 成交额 / 市值边界值。  
4. 无 `fundamentals_asof` 时不因商誉/暴雷误杀。  
5. `limit_up_in_universe=false` 时涨停标记不踢出股票池。  
6. 软过滤开关行为。

### 3.5 实现阶段涉及文件（批准本规格并完成 writing-plans 后）

- `src/astock_alpha/modules/m3_universe/snapshots.py`  
- `src/astock_alpha/modules/m3_universe/filters.py`  
- `src/astock_alpha/modules/m3_universe/universe.py`  
- `configs/strategy_v1_0.preregistered.json`（或新版本号配置）  
- `tests/test_universe.py`  
- 教训日志追加一条「安检共识对照」变更说明（非代码）

---

## 4. 明确排除

- 真实 SnapshotProvider / BaoStock / Tushare 适配器  
- 研究池与交易池分层  
- 模块 0 状态落盘、晋级审计  
- 模块 4+ 选股因子  

---

## 5. 规格自检记录

| 检查项 | 结果 |
|---|---|
| 无 TBD/TODO 占位 | 通过 |
| 与第 1–3 节用户确认内容一致 | 通过 |
| 涨跌停归属无矛盾 | 通过（池外硬踢关闭，字段留给 m6） |
| 范围可单次实现计划消化 | 通过（无数据源、无 m0 持久化） |
| 歧义：市值用总市值非流通市值 | 已明示保持 `total_market_cap` 绝对门槛 |
