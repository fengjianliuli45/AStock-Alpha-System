# BULL max_hold=5 — 复验（2026-08-12）

同批 59 笔 pullback 入选，用 `evaluate_ma_env_day` 日终模拟（含 T+1）。

| 方案 | 胜率 | 均值 | 中位 | 主出场 |
|---|---:|---:|---:|---|
| 改前 ma_env（仅 MA20+跟踪） | 35.6% | -0.56% | -2.35% | stop_loss 48 |
| **改后 + max_hold=5** | **54.2%** | **+0.32%** | **+0.29%** | time_stop 42 / stop_loss 17 |
| 对照：信号日后 +5 日收盘 | 59.3% | +0.36% | +0.57% | （无撮合） |

门槛：相对改前转正；接近 +5 日前向，未放宽 bias/止损。

## 宿主冒烟 2025-07～08（`scripts/smoke_bull_hold5_2025q3.py`）

- `2025-07-02` `open_book` n=1 **max_w=0.100**，`launch=pullback_ma10` / `exit=ma_env`
- `2025-07-09` `book_manage` → **`time_stop:sh.600120:1.00`**（入场后第 5 个交易日）
- `2025-08-11` `open_book` n=1 **max_w=0.100**
- `2025-08-18` → **`time_stop:sh.600585:1.00`**
- 汇总：opens=2，time_stop=2，stop_loss=0；日志 `artifacts/smoke_bull_hold5_2025q3.log`
