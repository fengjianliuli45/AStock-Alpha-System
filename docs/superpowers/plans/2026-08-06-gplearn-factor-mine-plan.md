# 实现计划：gplearn 小规模因子挖掘

依据：`docs/superpowers/specs/2026-08-06-gplearn-factor-mine-design.md`

教训约束：L-001 固定超参、OOS 只评估、禁止拧参复活；L-002 纯量价局限写进 README；不做完整撮合回测（L-006/L-007）。

---

## 任务

### 1. 脚手架与依赖

- `research/gplearn_mine/` 包结构
- `requirements-research.txt`：`gplearn`, `scikit-learn`, `pandas`, `numpy`, `pyarrow`
- README：路径、CLI、不可晋级声明

### 2. panel / features / evaluate / mine / run

- 按 spec §3–§6 实现
- CSI300 成分：本地文件优先；可选 gm；失败给出清晰错误
- 产物写入 `artifacts/gplearn_mine/<run_id>/`

### 3. 验收

- `python -m research.gplearn_mine.run` 退出 0
- 三份 JSON + 表达式可读

---

## 完成定义

与 spec §9 验收清单一致。
