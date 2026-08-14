# AStock-Alpha-System v1.0（框架骨架）

基于桌面设计文档《量化策略完整模块设计_v1.0》的模块化实现仓库。

**状态**：自建模块化框架；**m0 治理 + m3 股票池** 已实现，其余 stub；禁止实盘（`trading_enabled=false`）。

关联文档（桌面）：

- `量化策略完整模块设计_v1.0.md`
- `量化策略_教训与犯错日志.md`

## 模块映射

| ID | 模块 | 状态 |
|---|---|---|
| m0 | 治理与预注册 | ✅ 已实现 |
| m1 | Regime | ✅ 沪深300+中证500 双确认、2 日确认、恐慌恢复；情绪门控可选 |
| m2 | 板块选择 | stub |
| m3 | 股票池 | ✅ 安检对齐 + `a_share_5y` / `gm` SnapshotProvider |
| m4 | 基本面评分 | stub |
| m5 | 技术确认 | stub |
| m6 | 入场执行 | stub |
| m7 | 仓位分配 | stub |
| m8 | 出场管理 | stub |
| m9 | 组合风控 | stub |
| m10 | 监控熔断 | stub |

流水线顺序：`m0 → m1 → m2 → m3 → m4 → m5 → m7 → m6 → m8 → m9 → m10`

## 快速开始

```bash
cd D:\AI_Projects\Cursor\Cursor\AStock-Alpha-System
python -m pip install -e ".[dev]"
python -m astock_alpha.cli readiness
python -m astock_alpha.cli show-governance
python -m astock_alpha.cli run-once --asof 2026-07-17
pytest -q
```

日线数据默认路径（可改配置 `data.a_share_5y_root`）：

`D:/下载文件夹/a_share_5y`

说明：该库是 **五年前复权日线**。总市值由 Tushare 代理 `daily_basic.total_mv`（万元×1e4）补齐；token 读 `C:/Users/123/.tushare/token`，URL 见配置 `data.tushare_http_url`。解禁/减持/财务仍可能 `incomplete`。全市场扫描较慢，可用 `"max_symbols": 100` 做冒烟。


## 目录

```
configs/strategy_v1_0.preregistered.json   # 预注册参数（本地研究）
configs/strategy_v1_0.gm_backtest.json     # 掘金宿主回测示例
strategies/gm_astock_alpha.py              # 掘金策略入口
src/astock_alpha/
  gm_host/                                # 掘金 init/on_bar 宿主
  portfolio/signal_adapter.py             # 信号→目标权重
  modules/m0_governance/
  modules/registry.py
  pipeline/engine.py
  data/gm_provider.py                     # GmSnapshotProvider
  cli.py
tests/
```

## 治理硬约束（已编码）

- 参数冻结后改配置 → 报错，须新版本号
- 默认禁止交易；晋级门通过后才可 `enable_trading()`
- 连续 3 个样本外窗口 IR < -0.5 → 永久冻结

## 掘金宿主回测

设计：`docs/superpowers/specs/2026-08-05-gm-host-backtest-design.md`

将策略接进掘金终端做**日频回测**（信号级等权 Top-N，非完整 m6–m8；结果勿直接当晋级依据）。

```bash
pip install -e ".[dev,gm]"
# 终端保持登录；token 可用环境变量 GM_TOKEN，或配置 data.gm_token_path
set ASTOCK_ALPHA_CONFIG=configs\strategy_v1_0.gm_backtest.json
python strategies\gm_astock_alpha.py
```

或在掘金终端中把策略文件指向 `strategies/gm_astock_alpha.py`（需已 `pip install -e .` 以便 import `astock_alpha`）。

- 默认 `data.provider=gm`（指数/快照走掘金）；CLI 研究仍可用 `configs/strategy_v1_0.preregistered.json` 的 `a_share_5y`。
- 持仓：`universe` 按 `avg_amount_20d` Top-N（`portfolio.max_holdings`）等权，再乘 `regime_multiplier`，预留 `cash_floor`。
- 回测结束后看终端自带净值/回撤图。

## 下一阶段

仿真/实盘 Broker、正式 m6–m8 替换信号薄适配、晋级门 metrics 回灌。
