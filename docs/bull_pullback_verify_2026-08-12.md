# BULL 回踩选股 — 验收记录（2026-08-12）

## 设置
- `ASTOCK_M1_PLUGIN=index_ma`，`ASTOCK_SINGLE_CAP=0.10`，`ASTOCK_MAX_SYMBOLS=800`
- 前向：`scripts/forward_bull_min3_only.py` → `artifacts/forward_returns_bull_pullback.csv`
- 冒烟：本地 decide 扫描 2025-07-01～08-29（空仓才开，每约 8 日强制清簿以观察多次开仓）

## BULL 前向（2024-05-01～2026-01-31）

| 指标 | 最小三步（突破∩乖离） | 回踩后 |
|---|---:|---:|
| BULL 日 | 221 | 221 |
| 空仓日 / 空仓率 | 214 / **96.8%** | 174 / **78.7%** |
| 有票日占比 | ~3.2% | **21.3%**（≥15% 目标） |
| 入选笔数 | 9 | **59** |
| +5 日胜率 / 均值 | 55.6% / +3.89% | **59.3% / +0.36%** |
| +10 日胜率 / 均值 | 33.3% / +2.06% | 42.4% / -0.18% |
| +20 日胜率 / 均值 | 22.2% / -1.20% | 25.4% / -2.29% |
| max_w | 0.10 | **0.10** |
| exit 标签 | ma_env 9/9 | **ma_env 59/59** |
| launch | breakout/lock | pullback_ma10 44 / ma20 15 |

结论：覆盖率从 ~3% 升到 **21%**；有票样本 +5 日胜率仍 ≥45% 且均值 ≥0。未放宽 bias/止损。+10/+20 仍偏弱，属观察项，本轮不拧参。

## 2025Q3 冒烟（07～08）
- `2025-07-02`：`open_book` n=1 **max_w=0.100**，`launch=pullback_ma10`，bias5=-1.22%
- `2025-08-11`：`open_book` n=1 **max_w=0.100**，`launch=pullback_ma10`，bias5=2.31%，reason 含 `env=bull_trend`
- 日志：`artifacts/smoke_bull_pullback_2025q3.log`

## 单测
`tests/m3_universe/test_stock_selector_p0.py` + `tests/test_m4_technical.py`：**33 passed**
