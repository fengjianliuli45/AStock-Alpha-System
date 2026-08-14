# BULL 回踩选股（2026-08-12）

在最小三步（bias5≤3%、MA20/`exit=ma_env`、单票 10%）之上，把 BULL 启动从「突破/锁仓」改为「趋势完好 + 回踩 MA10/MA20 企稳」，并同步放宽 m4。

## 冻结规则

| 项 | 值 |
|---|---|
| 趋势基底 | 收盘 > MA20，且 MA20 近 5 日斜率 ≥ 0 |
| `pullback_ma10` | low ≤ MA10×1.01，收盘 ≥ MA10，量比 < 0.8 |
| `pullback_ma20` | low ≤ MA20×1.01，收盘 ≥ MA20，量比 < 0.7 |
| 排序 | 优先 ma10，再低量比，再高 accum |
| `bull_min_accum` | ≥ 2（回踩路径） |
| 保留 | bias5≤3%、`exit=ma_env`、单票 10%、最多 6 |
| m4 | reason 含 `launch=pullback_ma*` 放行；不追加 `exit=trend` |

**不做**：两档分批、分级止盈表、牛市三分子状态、SIDEWAYS 改动；**禁止**为覆盖率放宽 bias 或止损。

## 代码落点

- `src/.../m3_universe/stock_selector.py`：`_bull_pullback_setup` / `_bull_sort_and_select`
- `src/.../m4_technical/technical_confirmer.py`：`_passes(..., reason)`；BULL 回踩跳过 `TrendExitPlan`

## 验收摘要

见同日 `docs/bull_pullback_verify_2026-08-12.md`。
