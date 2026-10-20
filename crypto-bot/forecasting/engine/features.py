"""Causal one-minute features. Unknown historical microstructure stays missing."""
import hashlib
import json
import math
import numpy as np
import pandas as pd

SCHEMA = 1
HORIZONS = (5, 15, 60, 240, 1440)
MINUTE = 60_000
FEATURES = (
    'return1', 'return5', 'return15', 'return60', 'return240',
    'relative_volume', 'volume_acceleration', 'volatility15', 'volatility240',
    'compression', 'atr_pct', 'rsi', 'macd', 'ema_gap', 'adx',
    'resistance_distance', 'support_distance', 'taker_imbalance', 'trade_acceleration',
    'btc_relative60', 'eth_relative60', 'btc_correlation', 'correlation_change',
    'book_imbalance', 'spread_bps', 'liquidity_change', 'flow_imbalance',
    'funding_rate', 'open_interest_change', 'liquidation_usd',
)
AUX = ('book_imbalance', 'spread_bps', 'liquidity_change', 'flow_imbalance',
       'funding_rate', 'open_interest_change', 'liquidation_usd')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def checked_bars(raw, cutoff, historical=False):
    """Exact source identity is checked by caller; accept only completed regular bars."""
    if not isinstance(raw, list) or not raw or len(raw) > 500_000:
        raise ValueError('invalid_bar_count')
    rows = []
    seen = {}
    for item in raw:
        row = {}
        for key in ('time', 'open', 'high', 'low', 'close', 'volume'):
            value = item.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError('invalid_bar_' + key)
            row[key] = value
        stamp = row['time']
        if stamp <= 0 or stamp % MINUTE or row['low'] <= 0 or row['volume'] < 0 or not (
            row['low'] <= min(row['open'], row['close']) <= max(row['open'], row['close']) <= row['high']):
            raise ValueError('invalid_ohlcv')
        if stamp + MINUTE > cutoff:
            continue
        for key in ('quote_volume', 'trades', 'taker_buy_volume'):
            value = item.get(key)
            row[key] = float(value) if isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0 else None
        if stamp in seen and seen[stamp] != row:
            raise ValueError('conflicting_source_bar')
        seen[stamp] = row
    rows = sorted(seen.values(), key=lambda x: x['time'])
    if len(rows) < 241:
        raise ValueError('insufficient_completed_history')
    if not historical and (cutoff - rows[-1]['time'] - MINUTE < 0 or cutoff - rows[-1]['time'] - MINUTE > 120_000):
        raise ValueError('stale_completed_history')
    return rows


def feature_frame(rows, benchmark=None):
    df = pd.DataFrame(rows).set_index('time')
    c, h, l, v = (df[k] for k in ('close', 'high', 'low', 'volume'))
    log_returns = np.log(c).diff()
    out = pd.DataFrame(index=df.index)
    for n in (1, 5, 15, 60, 240):
        out[f'return{n}'] = c.pct_change(n, fill_method=None)
    out['relative_volume'] = v.rolling(5).mean() / v.shift(5).rolling(120).mean().replace(0, np.nan)
    out['volume_acceleration'] = v.rolling(5).mean() / v.shift(5).rolling(5).mean().replace(0, np.nan)
    out['volatility15'] = log_returns.rolling(15).std()
    out['volatility240'] = log_returns.rolling(240).std()
    out['compression'] = out.volatility15 / out.volatility240.replace(0, np.nan)
    tr = pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    out['atr_pct'] = atr / c
    delta = c.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    out['rsi'] = (100 - 100/(1 + gain/loss.replace(0, np.nan))).where(loss != 0, 100).where((gain+loss) != 0, 50)
    out['macd'] = (c.ewm(span=12, adjust=False).mean()-c.ewm(span=26, adjust=False).mean())/c
    out['ema_gap'] = (c.ewm(span=9, adjust=False).mean()/c.ewm(span=21, adjust=False).mean())-1
    up, down = h.diff(), -l.diff()
    plus = up.where((up > down) & (up > 0), 0).ewm(alpha=1/14, adjust=False).mean()/atr
    minus = down.where((down > up) & (down > 0), 0).ewm(alpha=1/14, adjust=False).mean()/atr
    out['adx'] = (100*(plus-minus).abs()/(plus+minus).replace(0, np.nan)).ewm(alpha=1/14, adjust=False).mean()
    out['resistance_distance'] = c/h.shift().rolling(60).max()-1
    out['support_distance'] = c/l.shift().rolling(60).min()-1
    out['taker_imbalance'] = 2*df.taker_buy_volume.rolling(5).sum()/v.rolling(5).sum().replace(0, np.nan)-1
    out['trade_acceleration'] = df.trades.rolling(5).mean()/df.trades.shift(5).rolling(120).mean().replace(0, np.nan)
    for name in ('btc', 'eth'):
        ref = benchmark.get(name) if benchmark else None
        if ref is not None:
            aligned = ref.reindex(out.index)  # exact timestamps; never backfill future data
            out[f'{name}_relative60'] = out.return60 - aligned.pct_change(60, fill_method=None)
            if name == 'btc':
                corr = log_returns.rolling(120).corr(np.log(aligned).diff())
                out['btc_correlation'] = corr
                out['correlation_change'] = corr-corr.shift(60)
    for name in FEATURES:
        if name not in out: out[name] = np.nan
    # A feature window crossing a missing minute is invalid, even if row counts look adequate.
    contiguous = pd.Series(df.index, index=df.index).diff().eq(MINUTE).rolling(240).sum().eq(240)
    out.loc[~contiguous, :] = np.nan
    return out.replace([np.inf, -np.inf], np.nan)


def latest_features(rows, auxiliary=None, now=None, benchmark=None):
    frame = feature_frame(rows, benchmark)
    values = frame.iloc[-1]
    if pd.isna(values['return240']) or pd.isna(values['atr_pct']):
        raise ValueError('gapped_feature_window')
    result = {key: float(values[key]) if pd.notna(values[key]) else None for key in FEATURES}
    for name in AUX:
        item = (auxiliary or {}).get(name)
        if not isinstance(item, dict): continue
        value, stamp = item.get('value'), item.get('observedAt')
        if isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value) and isinstance(stamp, (float, int)) and now is not None and 0 <= now-stamp <= 30_000:
            result[name] = float(value)
    return result


def targets(rows, index, horizon, features, cost_bps=40):
    end = index+horizon
    if end >= len(rows): return None
    window = rows[index+1:end+1]
    start = rows[index]['time'] + MINUTE
    if any(bar['time'] != start+i*MINUTE for i, bar in enumerate(window)): return None
    entry = window[0]['open']
    stop_pct = max(.001, float(features['atr_pct'])*1.5)
    target_pct = stop_pct*2
    stop, target = entry*(1-stop_pct), entry*(1+target_pct)
    hit, exit_price, elapsed, reason = 0, window[-1]['close'], horizon, 'expiration'
    for j, bar in enumerate(window):
        if bar['low'] <= stop:
            exit_price, elapsed, reason = min(stop, bar['open']), j+1, 'stop'; break
        if bar['high'] >= target:
            hit, exit_price, elapsed, reason = 1, target, j+1, 'target'; break
    final_return = window[-1]['close']/entry-1
    resistance = rows[index]['close']/(1+features['resistance_distance'])
    highest, lowest = max(x['high'] for x in window), min(x['low'] for x in window)
    future_returns = np.diff(np.log([entry]+[x['close'] for x in window]))
    breakout = highest >= resistance*(1+target_pct)
    reversal = (features['return15'] < 0 and final_return > target_pct) or (features['return15'] > 0 and final_return < -target_pct)
    return {'up': int(final_return > 0), 'breakout': int(breakout), 'reversal': int(reversal),
            'target_before_stop': hit, 'false_breakout': int(highest > resistance and window[-1]['close'] < resistance),
            'volatility_expansion': int(np.std(future_returns) > features['volatility15']*1.5),
            'return': final_return, 'volatility': float(np.std(future_returns)),
            'mfe': highest/entry-1, 'mae': lowest/entry-1,
            'modeled_net_return': exit_price/entry-1-cost_bps/10_000,
            'exit_reason': reason, 'time_to_event': elapsed, 'entry': entry,
            'label_end': start+horizon*MINUTE, 'target_pct': target_pct, 'stop_pct': stop_pct,
            'cost_bps': cost_bps, 'cost_basis': 'explicit_OHLC_research_assumption_not_executable_quote'}
