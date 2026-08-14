# BULL 持有衰减诊断与 5 日时间止损（2026-08-12）

## 诊断（59 笔回踩入选）

明细：`artifacts/bull_pullback_hold_path.csv`；脚本：`scripts/diag_bull_pullback_hold_path.py`

| 路径类 | n | 含义 |
|---|---:|---|
| peak_giveback | 25 (42%) | 峰值≥3% 后大幅回吐 |
| early_weak | 13 (22%) | 开仓即弱 |
| hold_ok / other / … | 其余 | — |

- 峰值中位日 **7**，MFE 均值 **+9.5%**，但 +20 日均值 **-2.3%**
- 20 日内触及 MA20 收盘止损 **86%**，中位第 **8** 日，止损收益均值 **-3.3%**（胜率仅 8%）
- 反事实：纯持有到 ma_env 结束 **胜率 35.6% / 均值 -0.56%**（48/59 为止损）；**第 5 日清仓** 约 **54% / +0.28%**

根因：短边有优势，长拿到 MA20 止损等于「先吐完再砍」。

## 冻结一小步（已落地）

- `MaEnvExitPlan.max_hold_days`：`bull_trend` / `bull_correction` = **5**
- 优先级仍为：止损 > 乖离 > 跟踪 > **时间** > 环境
- **不改**：bias5、MA20 止损垫、入场回踩规则

## 复验（同 59 笔 ma_env 日终模拟）

见 `docs/bull_hold5_verify_2026-08-12.md`。
