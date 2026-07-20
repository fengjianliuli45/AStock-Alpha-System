# m2_market_environment — 大盘环境综合评分模块

> 时间：2026-07-21 | 状态：设计文档 v1 | 对应需求：少主五大维度综合打分

---

## 1. 问题

现有 m1_regime 仅基于沪深300/中证500 的 MA60 斜率做区制分类（BULL/BEAR/SIDEWAYS/PANIC），外加涨跌停情绪门控。但真正的市场环境判断需要更多维度：

- 货币流动性（宏观）
- 场内资金面（市场交易）
- 全市场估值水位（安全边际）
- 市场情绪（赚钱效应）
- 经济基本面（支撑验证）

## 2. 方案：新建 m2_market_environment 模块

**不改 m1**。新建 `m2_market_environment`，m1 降级为它的情绪子维度。

### 模块结构

```
src/astock_alpha/modules/m2_market_environment/
├── __init__.py          # ModuleEntry 导出
├── environment.py       # MarketEnvironmentModule（主入口）
├── dimensions/
│   ├── __init__.py
│   ├── liquidity.py     # 维度1: 货币流动性
│   ├── capital.py       # 维度2: 场内资金面
│   ├── valuation.py     # 维度3: 全市场估值水位
│   ├── sentiment.py     # 维度4: 市场情绪（包装 m1 输出）
│   └── fundamentals.py  # 维度5: 经济基本面
├── scoring.py           # 综合打分引擎
└── data/
    ├── __init__.py
    └── tushare_macro.py # Tushare 宏观数据采集
```

### 流水线位置

现有顺序：`m0 → m1 → m2 → m3 → m4 → m5 → m7 → m6 → m8 → m9 → m10`

新 m2 插入在 m0 之后、m1 之前（环境评级影响全流程）：

`m0 → **m2** → m1 → m3 → m4 → m5 → m7 → m6 → m8 → m9 → m10`

理由：大盘环境决定了后续所有模块的运作模式，优先计算。

---

## 3. 五个维度的详细打分规则

### 维度1: 货币流动性（权重 25%）

| 指标 | 数据源 | 偏多 | 中性 | 偏空 | 子权重 |
|------|--------|------|------|------|--------|
| M1同比增速（近60日滚动均值） | Tushare `money_supply` | 近5年分位>60% 或连续3月上行 | 20%~60% | <20% 或连续3月下行 | 30% |
| M1-M2剪刀差 | Tushare `money_supply` | 由负转正或分位>50% | -3%~0震荡 | 持续扩大且分位<20% | 25% |
| DR007短端利率（近20日均值） | Tushare `shibor` | 近3年分位<30% | 30%~70% | >80%资金面紧张 | 25% |
| 社融存量同比（近3月均值） | Tushare `cn_m` / 宏观 | 分位>50%且连续2月回升 | 30%~50% | <30%持续下行 | 20% |

> Tushare 接口：`money_supply`(M1/M2)、`shibor`(DR007)、`cn_m`(社融)

得分归一化：各子指标 0-100 分，按权重加权 → 维度得分 0-100。

### 维度2: 场内资金面（权重 20%）

| 指标 | 数据源 | 偏多 | 中性 | 偏空 | 子权重 |
|------|--------|------|------|------|--------|
| 北向资金近20日累计净流入 | Tushare `margin` / 北向 | 累计>300亿，近2年分位>70% | -100~+300亿 | 累计流出>200亿，分位<20% | 30% |
| 融资余额近20日增速 | Tushare `margin_detail` | 增速>3%，分位>70% | -1%~+3% | <-2%，分位<20% | 25% |
| 两市近5日日均成交额 | Tushare `daily_basic` 聚合 | 日均>10000亿，分位>70% | 7000~10000亿 | <6000亿，分位<30% | 25% |
| 全市场主力资金近5日净额 | Tushare `moneyflow` | 连续3日净流入，累计>500亿 | ±300亿内 | 连续3日净流出，累计>400亿 | 20% |

### 维度3: 全市场估值水位（权重 20%）

| 指标 | 数据源 | 偏多 | 中性 | 偏空 | 子权重 |
|------|--------|------|------|------|--------|
| 万得全A PE-TTM分位 | Tushare `index_daily` + 全市场 | 近10年分位<30% | 30%~70% | >70% | 35% |
| 全市场风险溢价（1/PE - 10Y国债） | Tushare `index_daily` + `bond` | 分位>70%，股票性价比高 | 30%~70% | <30% | 35% |
| 全市场破净股占比 | Tushare `daily_basic` | >8% 底部信号 | 3%~8% | <1% 过热 | 30% |

### 维度4: 市场情绪（权重 20%）

**直接复用 m1_regime 的产出**，不重复采集。从 m1 的 Audit 信息中提取：

| 指标 | 来源 | 偏多 | 中性 | 偏空 | 子权重 |
|------|------|------|------|------|--------|
| 区制（regime） | m1 state.regime | BULL | SIDEWAYS | BEAR/PANIC | 30% |
| 涨跌比 | m1 sentiment.advance_decline_ratio | >2:1 | 1:2~2:1 | <1:2 | 20% |
| 涨停占比分位 | m1 limit_up_ratio_zscore | >0.5 | 0.2~0.5 | <0.2 | 20% |
| 跌停占比分位 | m1 limit_down_ratio_zscore | <0.2 | 0.2~0.5 | >0.5 | 20% |
| 情绪门控信号 | m1 forbid_chase / tighten / cautious | 无+ | 一个+ | 多个+ | 10% |

> 情绪维度不走 Tushare，在 pipeline 中从 m1 的 state.meta["sentiment"] 读取。

### 维度5: 经济基本面（权重 15%）

| 指标 | 数据源 | 偏多 | 中性 | 偏空 | 子权重 |
|------|--------|------|------|------|--------|
| 制造业PMI | Tushare `cn_pmi` | >50连续2月回升 | 49~50 | <49持续下行 | 40% |
| PPI同比 | Tushare `cn_ppi` | 转正或连续3月上行 | -2%~1% | <-3%持续下行 | 30% |
| CPI同比 | Tushare `cn_cpi` | 1%~2%温和通胀 | 0~1%/2%~3% | >3%高通胀 | 30% |

---

## 4. 综合打分引擎（scoring.py）

### 计算方法

```
综合得分 = Σ(维度得分 × 维度权重)
```

各维度分数范围 0-100，综合得分同样 0-100。

### 综合环境评级

| 综合得分 | 评级 | 描述 |
|---------|------|------|
| ≥70 | 强多头（BULL_STRONG） | 资金宽松、估值安全、情绪健康 → 偏成长/动量/高弹性 |
| 50~70 | 偏多（BULL_WEAK） | 多数维度偏正但非一致 → 偏质量+估值合理 |
| 30~50 | 偏空（BEAR_WEAK） | 中性偏弱，部分维度承压 → 偏防御+低波动 |
| ≤30 | 强空头（BEAR_STRONG） | 多维度全面承压 → 高股息+防御+极低仓位 |

震荡区间（30~70分）由具体子维度的强弱方向决定细节。

### 输出到 PipelineState

```python
@dataclass
class EnvironmentScore:
    composite_score: float          # 0-100
    rating: str                     # BULL_STRONG / BULL_WEAK / BEAR_WEAK / BEAR_STRONG
    dimension_scores: dict[str, float]  # {"liquidity": 65, "capital": 72, ...}
    dimension_details: dict[str, dict]  # 每个维度的明细指标数值
    
# 写入 state.meta["m2_environment"]
state.meta["m2_environment"] = env_score
```

---

## 5. m3_universe 联动

m3 的 `universe.py` 中硬过滤基础上，增加**环境适配池**：

```python
def apply_environment_filter(
    universe: pd.DataFrame,
    env: EnvironmentScore,
) -> pd.DataFrame:
    """根据大盘环境评级，叠加不同的选股条件范围"""
    if env.rating == "BULL_STRONG":
        # 成长动量：换手>3%、成交>5000万、净利润增速>20%、站稳MA60
        ...
    elif env.rating == "BULL_WEAK":
        # 质量优先：ROE>10%、PE行业分位<50%、波动率低
        ...
    elif env.rating == "BEAR_WEAK":
        # 防御：股息率>3%、PE<15倍、资产负债率<50%
        ...
    else:  # BEAR_STRONG
        # 极防御：上证50+沪深300成分股、股息>3%、贝塔<0.8
        ...
```

具体过滤条件见少主之前写的「不同大盘环境下的个股筛选条件与范围」。

---

## 6. 数据获取策略

### 实时模式（每日运行）

- 宏观/基本面数据（M1、社融、PMI等）：每月公布一次，可用缓存策略
- 资金面/交易数据（北向、融资、成交额）：每日更新
- 估值数据（PE分位、破净率）：每日更新
- 情绪数据：从 m1 输出直接读取，无需额外请求

### Tushare 调用策略

- 优先使用本地缓存（data/macro_cache/），每日一次增量更新
- 按维度分组调用，失败维度自动降级（不影响其他维度的计算）
- 缓存过期时间：宏观 1天 / 基本面 1天 / 资金面一天内可多次

---

## 7. 配置参数

```json
{
  "modules": {
    "m2_market_environment": {
      "enabled": true,
      "weights": {
        "liquidity": 0.25,
        "capital": 0.20,
        "valuation": 0.20,
        "sentiment": 0.20,
        "fundamentals": 0.15
      },
      "thresholds": {
        "bull_strong": 70,
        "bear_strong": 30
      },
      "data": {
        "tushare_token_path": "C:/Users/123/.tushare/token",
        "macro_cache_root": "data/macro_cache"
      }
    }
  }
}
```

---

## 8. 实现计划

| 步骤 | 文件 | 内容 |
|------|------|------|
| 1 | data/tushare_macro.py | 宏观数据采集：M1、DR007、社融、北向、融资、成交额、PMI、PPI、CPI、PE分位 |
| 2 | dimensions/liquidity.py | 维度1：货币流动性打分 |
| 3 | dimensions/capital.py | 维度2：场内资金面打分 |
| 4 | dimensions/valuation.py | 维度3：全市场估值水位打分 |
| 5 | dimensions/sentiment.py | 维度4：包装 m1 情绪输出 |
| 6 | dimensions/fundamentals.py | 维度5：经济基本面打分 |
| 7 | scoring.py | 综合打分引擎 |
| 8 | environment.py | 主模块入口 + PipelineState 输出 |
| 9 | __init__.py | 导出 + registry 注册 |
| 10 | m3_universe filters | 增加环境适配选股池 |
| 11 | 测试 | 各维度的单元测试 |
