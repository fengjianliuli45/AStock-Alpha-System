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
| m3 | 股票池 | ✅ 安检对齐 + `a_share_5y` 日线 SnapshotProvider（见 `data.a_share_5y_root`） |
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
configs/strategy_v1_0.preregistered.json   # 预注册参数（冻结源）
src/astock_alpha/
  modules/m0_governance/                  # 晋级门 / 死亡线 / 参数哈希
  modules/stubs.py                        # m1–m10 占位
  modules/registry.py                     # 模块装配与顺序
  pipeline/engine.py                      # 编排
  data/contracts.py                       # PIT 契约占位
  cli.py
tests/
```

## 治理硬约束（已编码）

- 参数冻结后改配置 → 报错，须新版本号
- 默认禁止交易；晋级门通过后才可 `enable_trading()`
- 连续 3 个样本外窗口 IR < -0.5 → 永久冻结

## 下一阶段（Phase 1 业务）

按设计路线图实现 **m3 股票池硬过滤**（ST / 上市天数 / 成交额 / 市值 / 解禁等），仍不开启实盘。
