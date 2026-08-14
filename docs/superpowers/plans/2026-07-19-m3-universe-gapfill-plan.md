# 实现计划：m3 安检对齐查漏补缺

依据：`docs/superpowers/specs/2026-07-19-m3-universe-gapfill-design.md`

## 任务

1. `StockSnapshot` 增加 `is_suspended`、`fundamentals_asof`
2. `UniverseFilterConfig` 增加 `enforce_suspension`、`limit_up_in_universe`
3. `evaluate_stock`：停牌硬安检；财务 PIT 门闩；涨跌停默认不硬踢
4. 预注册 JSON 同步新键（版本仍 v1.0，参数表补全）
5. 扩展 `test_universe.py` 覆盖规格测试清单
6. 教训日志变更一行；规格状态改为已批准并实现中/完成

## 验收

`python -m pytest -q` 全部通过。
