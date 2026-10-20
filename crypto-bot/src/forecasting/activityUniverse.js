// Venue identity, native event time and observed activity. No profit probabilities.
export class ActivityUniverse {
  constructor({ maxAgeMs = 30_000, maxSamples = 120, minQuoteVolume = 1_000_000 } = {}) {
    this.maxAgeMs = maxAgeMs; this.maxSamples = maxSamples; this.minQuoteVolume = minQuoteVolume;
    this.directory = new Map(); this.observations = new Map(); this.lastAnalyzed = new Map();
    this.rejections = {}; this.directoryAt = 0;
  }

  reject(code) { this.rejections[code] = (this.rejections[code] || 0) + 1; return false; }

  setDirectory(payload, now = Date.now()) {
    if (!Array.isArray(payload?.symbols) || !payload.symbols.length) throw new Error('instrument_directory_unavailable');
    const next = new Map();
    for (const row of payload.symbols) {
      if (!/^[\p{L}\p{N}]{3,40}$/u.test(row.symbol || '') || !row.baseAsset || !row.quoteAsset || next.has(row.symbol)) throw new Error('invalid_directory_identity');
      next.set(row.symbol, { pair: row.symbol, base: row.baseAsset, quote: row.quoteAsset,
        instrument: `binance:spot:${row.symbol}`, active: row.status === 'TRADING' && row.isSpotTradingAllowed === true });
    }
    this.directory = next; this.directoryAt = now;
    for (const pair of this.observations.keys()) if (!next.get(pair)?.active) this.observations.delete(pair);
  }

  observe(frame, now = Date.now()) {
    const identity = this.directory.get(frame?.s);
    if (!identity?.active) return this.reject('unknown_or_inactive_pair');
    const stamp = Number(frame.E), price = Number(frame.c), quoteVolume = Number(frame.q);
    if (!Number.isFinite(stamp) || stamp <= 0 || stamp > now || now-stamp > this.maxAgeMs) return this.reject('stale_future_or_missing_native_time');
    if (!(price > 0) || !(quoteVolume >= 0)) return this.reject('invalid_market_observation');
    const previous = this.observations.get(identity.pair);
    if (previous && stamp <= previous.observedAt) return this.reject('out_of_order_or_duplicate');
    const history = previous?.history || [];
    if (!history.length || stamp-history.at(-1).time >= 15_000) history.push({ time: stamp, price, rolling24hQuoteVolume: quoteVolume });
    while (history.length > this.maxSamples) history.shift();
    this.observations.set(identity.pair, { ...identity, price, quoteVolume, observedAt: stamp, receivedAt: now, history });
    return true;
  }

  candidates(now = Date.now(), limit = 12) {
    const rows = [];
    for (const row of this.observations.values()) {
      if (!this.directory.get(row.pair)?.active || now-this.directoryAt > 26*3_600_000
          || now-row.observedAt < 0 || now-row.observedAt > this.maxAgeMs || !['USDT', 'USDC'].includes(row.quote)
          || row.quoteVolume < this.minQuoteVolume) continue;
      const history = row.history.filter(x => now-x.time <= 30*60_000);
      if (!history.length) continue;
      const baseline = history[0], recent = history.filter(x => now-x.time <= 60_000);
      const move = row.price/baseline.price-1;
      const shortMove = recent.length > 1 ? row.price/recent[0].price-1 : 0;
      // Rolling 24h turnover change is explicitly a proxy, not new traded volume.
      const volumeProxy = baseline.rolling24hQuoteVolume > 0 ? row.quoteVolume/baseline.rolling24hQuoteVolume-1 : 0;
      const reason = volumeProxy > .01 && Math.abs(move) < .005 ? 'turnover_change_before_price_expansion'
        : Math.abs(shortMove) > .001 ? 'short_window_activity' : 'liquid_universe_rotation';
      const priority = Math.min(5, Math.max(0, volumeProxy)*100) + Math.min(3, Math.abs(shortMove)*100)
        + Math.min(2, (now-(this.lastAnalyzed.get(row.pair) || 0))/3_600_000);
      rows.push({ ...row, history: undefined, reason, priority, movementBeforeAlert: move,
        observedWindowMinutes: (row.observedAt-baseline.time)/60_000,
        stage: 'EARLY WATCH', activityIsProbability: false,
        alreadyExpanded: Math.abs(move) >= .01, quoteVolumeCurrency: row.quote,
        accountTradability: 'unverified', newlyObserved: history.length < 20 });
    }
    return rows.sort((a, b) => b.priority-a.priority || a.pair.localeCompare(b.pair)).slice(0, limit);
  }

  markAnalyzed(pair, now = Date.now()) { this.lastAnalyzed.set(pair, now); }
  diagnostics(now = Date.now()) {
    return { directory: this.directory.size, activeSpot: [...this.directory.values()].filter(r => r.active).length,
      observed: this.observations.size, freshObserved: [...this.observations.values()].filter(r => 0 <= now-r.observedAt && now-r.observedAt <= this.maxAgeMs).length,
      rejectedObservations: { ...this.rejections }, scope: 'Venue-specific monitoring, not every cryptocurrency or USD-converted liquidity.' };
  }
}

export function dexPairObservation(pair, receivedAt = Date.now()) {
  if (!pair?.chainId || !pair.pairAddress || !pair.baseToken?.address) throw new Error('missing_chain_contract_identity');
  return { instrument: `dex:${pair.chainId}:${pair.pairAddress}`, chain: pair.chainId, pairAddress: pair.pairAddress,
    tokenAddress: pair.baseToken.address, symbol: pair.baseToken.symbol || null,
    price: Number(pair.priceUsd) > 0 ? Number(pair.priceUsd) : null,
    liquidityUsd: Number(pair.liquidity?.usd) >= 0 ? Number(pair.liquidity.usd) : null,
    providerObservedAt: null, receivedAt, timestampBasis: 'receipt_only_not_native_quote_time',
    eligibleForForecast: false, reason: 'Emerging discovery only; timestamped candles, identity/contract and execution risk evidence required.' };
}
