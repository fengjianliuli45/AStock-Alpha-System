# BULL early_weak 量价因子离线挖掘（2026-08-12）

## 目标
在回踩入选样本上，挖能降低 `early_weak` / 短窗止损 / 五日亏损的量价硬过滤候选。  
**不做**：直接改线上参数；样本外未过线不接入。

## 样本与标签
- 面板：`artifacts/bull_early_weak_factor_panel.csv`（n=59，与 `bull_pullback_hold_path` 对齐）
- 摘要：`artifacts/bull_early_weak_factor_summary.csv`
- 脚本：`scripts/mine_bull_early_weak_factors.py`
- 基线：`y_bad`≈45.8%，`early_weak`≈22%，`stop5`≈28.8%，`ret5` 均值 +0.36%

## 相对有效（样本内分位门，按坏票率下降排序）

| 因子 | 公式含义 | 建议方向 | IC(ret5) | 坏票率下降 | 保留后 ret5 |
|---|---|---|---:|---:|---:|
| `close_vs_max10` | close/近10日最高-1 | 越大越好（≥p40） | +0.21 | **-14.3pp** | +1.81% |
| `ma20_slope_5` | MA20/前移5日MA20-1 | 越大越好 | +0.20 | -8.6pp | +0.99% |
| `bias_ma10` | close/MA10-1 | 越大越好（仍须≤bias5硬顶） | +0.08 | -8.6pp | +0.99% |
| `below_ma20_frac10` | 近10日收盘<MA20占比 | 越小越好 | -0.11 | -6.7pp | +0.53% |
| `low_vs_min10` | low/近10日最低-1 | 越大越好（未创新低） | +0.13 | -2.9pp | +0.80% |

量比类（`vol_ratio_20` / `amt_ratio_20`）在本样本提升很弱——回踩规则已含缩量，边际有限。  
`stabilize_score` / `lower_shadow` 本次未进推荐（lift 不足或伤害收益）。

## 建议接入顺序（仍需样本外）
1. **先试一条**：`close_vs_max10 >= -4%` 左右（近高回撤不过深）或 `ma20_slope_5 > 0`（加强趋势基底）
2. 同窗簿级复验：止损占比↓、BULL 开仓均值改善
3. 未过线不叠加第二条

## 限制
n=59 偏小；分位阈值为**样本内**，禁止直接当生产阈值。扩大样本或切时间做 OOS 后再冻结进 m3。
