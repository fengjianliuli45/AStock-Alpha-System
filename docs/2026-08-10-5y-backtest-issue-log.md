# 五年回测问题记录（m1 指数锚定后）

> 后续统一追加到：[`docs/问题与修复记录.md`](./问题与修复记录.md)  
> 项目：`D:\app\astock-alpha-new`  
> 策略 ID：`875ad98a-93ff-11f1-9729-a0ad9f23dffe`  
> 区间：2021-07-20 → 2026-08-04  
> 启动命令：`python scripts/run_gm_5y_backtest.py`  
> 关联改动：m1 沪深300 MA 锚定 / BULL 反延伸选股 / m6 持仓簿宿主  

---

## 运行元信息

| 项 | 值 |
|---|---|
| 开始时间 | 2026-08-10 19:12 首次失败；19:13 重试成功进入回测 |
| 结束时间 | 2026-08-10 21:48:54 |
| 耗时 | 约 2.6 小时（重试成功后） |
| 退出码 | `0` |
| 控制台日志 | `artifacts/gm_5y_backtest_console.log` |
| 宿主日志 | `artifacts/gm_host_runtime.log` |
| Commit | `f0f7539` feat(m1/gm_host): HS300 regime, BULL selection, m6 host wiring |
| 收尾 | `init warm ok symbols=5394 hs300=1844`；跑满至 `on_bar 2026-08-04 #1222` |

---

## 结论摘要

- 五年回测 **正常跑完**（`EXIT=0`），本轮运行中未见新的策略崩溃 / `GmError 1018`。
- 唯一阻塞是启动时的 **P-01（1300 连终端）**，重试后恢复。
- 绩效曲线与汇总指标请在掘金终端查看（控制台几乎不刷净值数字）。

---

## 问题与解决

### P-01 — GmError 1300：初始化回测失败（无法连接终端）
- **时间**：2026-08-10 19:12
- **现象**：`python scripts/run_gm_5y_backtest.py` 启动约 20s 后抛出  
  `GmError status=1300`，消息：`初始化回测失败，可能是终端未启动或无法连接到终端`。
- **原因**：本机虽有 `goldminer3.exe` / `gmterm-serv.exe` 进程，但 SDK `run()` 未能完成与终端回测服务握手（常见于终端忙、服务未就绪、或上一轮回测残留锁）。
- **处理**：确认本机已有 `goldminer3` / `gmterm-serv`；不改策略代码，约 1 分钟后直接重试 `run_gm_5y_backtest.py`。
- **结果**：重试成功并完整跑到 2026-08-04；最终退出码 0。

### P-02 — 控制台长时间停在「正下载数据…」易误判卡住
- **时间**：全程
- **现象**：`gm_5y_backtest_console.log` 启动后几乎不再更新，看起来像卡在数据下载。
- **原因**：掘金 SDK 启动阶段提示后不再往 stdout 刷日进度；真实进度写在 `gm_host_runtime.log` 的 `on_bar`。
- **处理**：用 `Get-Content artifacts\gm_host_runtime.log -Tail 5` 看交易日推进；不据此杀进程。
- **结果**：实际持续推进至期末，属显示问题而非死锁。

---
