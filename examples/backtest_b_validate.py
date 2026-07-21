#!/usr/bin/env python3
"""
B 组方案验证回测
本机独立运行，不走 OpenClaw exec 管道
"""
import sys, akshare as ak, pandas as pd
from pathlib import Path
sys.path.insert(0, '/mnt/hgfs/host_downloads/AStock-Alpha-System/src')
from astock_alpha.modules.m1_regime.classify import RegimeStateMachine, classify_index_raw, combine_raw
from astock_alpha.types import Regime
from collections import Counter

hs300 = ak.stock_zh_index_daily(symbol='sh000300')
hs300['date'] = hs300['date'].astype(str).str[:10]
hs300 = hs300.sort_values('date').set_index('date')['close'].astype(float)
print(f'HS300: {len(hs300)} 天', flush=True)

csi500 = ak.stock_zh_index_daily(symbol='sh000905')
csi500['date'] = csi500['date'].astype(str).str[:10]
csi500 = csi500.sort_values('date').set_index('date')['close'].astype(float)
print(f'CSI500: {len(csi500)} 天', flush=True)

common = sorted(set(hs300.index) & set(csi500.index))
hs300 = hs300.loc[common]
csi500 = csi500.loc[common]
dates = common[-1300:]
N = len(dates)
print(f'公共区间: {dates[0]} ~ {dates[-1]}, {N} 天', flush=True)

print('计算 raw classify...', flush=True)
raw_seqs = []
for d in dates:
    hs = hs300.loc[:d]
    zz = csi500.loc[:d]
    hs_raw = classify_index_raw(hs, ma_window=20, sideways_band=0.02)
    zz_raw = classify_index_raw(zz, ma_window=20, sideways_band=0.02)
    raw_seqs.append(combine_raw(hs_raw, zz_raw, bear_mode='both'))

print('加载 breadth...', flush=True)
DATA_DIR = Path('/mnt/hgfs/host_downloads/a_share_5y/qfq')
files = sorted(DATA_DIR.glob('SHSE.*.parquet'))[:500]
chunks = []
for f in files:
    df = pd.read_parquet(f, columns=['date', 'pctChg'])
    chunks.append(df)
panel = pd.concat(chunks, ignore_index=True)
panel['pctChg'] = panel['pctChg'].astype(float)
panel['date'] = panel['date'].astype(str).str[:10]
panel = panel[panel['date'].isin([str(d)[:10] for d in dates])]
pct_by_date = {d: panel[panel['date']==d]['pctChg'].values for d in panel['date'].unique()}
breadths = []
for d in dates:
    ds = str(d)[:10]
    arr = pct_by_date.get(ds)
    if arr is not None and len(arr) > 0:
        adv = float((arr > 0).sum())
        dec = float((arr < 0).sum())
        ad_ratio = adv / dec if dec > 0 else float('inf')
        panic = float((arr <= -5.0).mean())
        breadths.append({'advance_decline_ratio': ad_ratio, 'panic_ratio': panic, 'available': True})
    else:
        breadths.append(None)

print('运行状态机...', flush=True)
sm = RegimeStateMachine(confirm_days=1, min_hold_days=1)
c, r = sm.walk(raw_seqs, [True]*N, breadth_seq=breadths)
cv = [x.value for x in c]

rets = [0.0]
for i in range(1, N):
    ret = (hs300.loc[dates[i]] / hs300.loc[dates[i-1]] - 1.0) * 100
    rets.append(ret)

# B组方案：日内跌≥1%强制BEAR
final_regime = []
for i in range(N):
    if rets[i] <= -1.0:
        final_regime.append('bear')
    else:
        final_regime.append(cv[i])

print(f'最终分布: {dict(Counter(final_regime))}', flush=True)

# A组：仅BULL开仓
net_a = [1.0]
net_b = [1.0]
net_c = [1.0]
trades_a = 0
trades_b = 0

for i in range(1, N):
    ret = rets[i] / 100.0
    
    # A组：仅BULL
    r_a = ret if final_regime[i] == 'bull' else 0.0
    if final_regime[i] == 'bull':
        trades_a += 1
    
    # B组：BEAR=0, SIDEWAYS=0.5, BULL=1.0
    if final_regime[i] == 'bear':
        r_b = 0.0
    elif final_regime[i] == 'sideways':
        r_b = ret * 0.5
    else:
        r_b = ret
        trades_b += 1
    
    # C组：满仓
    r_c = ret
    
    net_a.append(net_a[-1] * (1 + r_a))
    net_b.append(net_b[-1] * (1 + r_b))
    net_c.append(net_c[-1] * (1 + r_c))

def stats(net):
    total_ret = (net[-1] - 1) * 100
    days = len(net) - 1
    ann_ret = (net[-1] ** (252 / days) - 1) * 100
    peak = net[0]
    max_dd = 0
    for v in net:
        if v > peak: peak = v
        dd = (v - peak) / peak * 100
        if dd < max_dd: max_dd = dd
    return total_ret, ann_ret, max_dd

print()
print('=== B 组方案验证结果 ===')
print(f'区间: {dates[0]} ~ {dates[-1]}, {N-1} 交易日')
print()
for label, net, trades in [('A组(仅BULL)', net_a, trades_a), ('B组(非BEAR,SIDEWAYS半仓)', net_b, trades_b), ('C组(买入持有)', net_c, N-1)]:
    total, ann, dd = stats(net)
    print(f'{label}')
    print(f'  总收益: {total:.1f}%  年化: {ann:.1f}%  最大回撤: {dd:.1f}%  交易天数: {trades}')

print()
print('done')
