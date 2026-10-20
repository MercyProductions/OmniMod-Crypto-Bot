import WebSocket from 'ws';
import { ActivityUniverse, dexPairObservation } from './activityUniverse.js';
import { ForecastClient, forecastEmbed, alertKey, boundedJson } from './forecastClient.js';
import { readMarketSnapshot, writeMarketSnapshot } from '../storage.js';

const BINANCE = 'https://data-api.binance.vision';
const COINBASE = 'https://api.exchange.coinbase.com';
const MINUTE = 60_000;
const reasonCode = error => /^[a-z_0-9:]{1,150}$/.test(error?.message || '') ? error.message : 'unexpected_data_or_worker_error';

export class PublicRequestBudget {
  constructor({ limit = 12, clock = Date.now, fetchImpl = fetch } = {}) {
    this.limit = limit; this.clock = clock; this.fetch = fetchImpl; this.states = new Map(); this.latencies = [];
    this.requests = 0; this.failures = 0;
  }
  async json(url) {
    const host = new URL(url).host, now = this.clock();
    const state = this.states.get(host) || { start: now, used: 0, cooldown: 0 };
    if (now-state.start >= MINUTE) { state.start = now; state.used = 0; }
    this.states.set(host, state);
    if (now < state.cooldown || state.used >= this.limit) throw new Error('provider_local_budget_or_cooldown');
    state.used++; this.requests++;
    const started = performance.now();
    try {
      const response = await this.fetch(url, { redirect: 'error', signal: AbortSignal.timeout(12_000), headers: { accept: 'application/json' } });
      const reportedWeight = response.headers.get('x-mbx-used-weight-1m');
      if (reportedWeight !== null && Number.isFinite(Number(reportedWeight))) state.reportedWeightLastMinute = Number(reportedWeight);
      if (!response.ok) {
        const retry = Number(response.headers.get('retry-after'));
        if ([403, 451].includes(response.status)) state.cooldown = now+3_600_000;
        else if ([418, 429].includes(response.status)) state.cooldown = now+Math.max(60, Math.min(86_400, Number.isFinite(retry) ? retry : 60))*1000;
        throw new Error(`public_provider_http_${response.status}`);
      }
      if (Number(response.headers.get('content-length')) > 12_000_000) throw new Error('public_response_limit');
      return await boundedJson(response, 12_000_000);
    } catch (error) { this.failures++; throw error; }
    finally { this.latencies.push(performance.now()-started); if (this.latencies.length > 200) this.latencies.shift(); }
  }
  diagnostics() {
    return { requests: this.requests, failures: this.failures, configuredRequestsPerMinutePerHost: this.limit,
      meanLatencyMs: this.latencies.length ? this.latencies.reduce((a, b) => a+b, 0)/this.latencies.length : null,
      providers: Object.fromEntries([...this.states].map(([host, state]) => [host, { ...state }])) };
  }
}

export function binanceMinuteBars(payload, now = Date.now()) {
  if (!Array.isArray(payload)) throw new Error('invalid_binance_candles');
  return payload.map(r => ({ time: Number(r[0]), open: Number(r[1]), high: Number(r[2]), low: Number(r[3]), close: Number(r[4]),
    volume: Number(r[5]), quote_volume: Number(r[7]), trades: Number(r[8]), taker_buy_volume: Number(r[9]) }))
    .filter(r => r.time+MINUTE <= now).sort((a, b) => a.time-b.time);
}

export function coinbaseMinuteBars(payload, now = Date.now()) {
  if (!Array.isArray(payload)) throw new Error('invalid_coinbase_candles');
  return payload.map(r => ({ time: Number(r[0])*1000, low: Number(r[1]), high: Number(r[2]), open: Number(r[3]), close: Number(r[4]), volume: Number(r[5]) }))
    .filter(r => r.time+MINUTE <= now).sort((a, b) => a.time-b.time);
}

export class ForecastResearchWorker {
  constructor({ token, url, sources = ['binance', 'coinbase'], maxCandidates = 6, dexEnabled = false,
    onForecast = null, budget = new PublicRequestBudget(), clock = Date.now, websocket = WebSocket } = {}) {
    this.client = new ForecastClient({ token, url }); this.sources = sources;
    if (!Array.isArray(sources) || !sources.length || sources.some(source => !['binance', 'coinbase'].includes(source))) throw new Error('unsupported_forecast_discovery_source');
    this.maxCandidates = Math.max(1, Math.min(12, maxCandidates)); this.dexEnabled = dexEnabled;
    this.onForecast = onForecast; this.budget = budget; this.clock = clock; this.WebSocket = websocket;
    this.universe = new ActivityUniverse(); this.socket = null; this.reconnect = null; this.stopped = false;
    this.coinbaseProducts = []; this.coinbaseAt = 0; this.coinbaseCursor = 0; this.dexAt = 0;
    this.coverage = {}; this.streamStatus = 'not_started'; this.flow = new Map(); this.tradeIds = new Map();
    this.detailSocket = null; this.detailPairs = []; this.connectFailures = 0;
  }

  connectStream() {
    if (this.stopped || !this.sources.includes('binance') || this.socket) return;
    // One aggregate stream covers venue activity, not one socket per asset.
    const socket = new this.WebSocket('wss://data-stream.binance.vision/ws/!miniTicker@arr', { handshakeTimeout: 12_000 });
    this.socket = socket;
    socket.on('open', () => { this.streamStatus = 'connected'; this.connectFailures = 0; });
    socket.on('message', frame => {
      try { const rows = JSON.parse(String(frame)); for (const row of Array.isArray(rows) ? rows : []) this.universe.observe(row, this.clock()); }
      catch { this.universe.reject('malformed_stream_frame'); }
    });
    socket.on('error', error => { this.streamStatus = /403|451|restricted|eligib/i.test(error.message) ? 'restricted' : 'stream_error'; });
    socket.on('close', () => {
      if (this.socket === socket) this.socket = null;
      if (!this.stopped) {
        const delay = this.streamStatus === 'restricted' ? 3_600_000 : Math.min(300_000, 5000*2**Math.min(6, this.connectFailures++));
        this.reconnect = setTimeout(() => this.connectStream(), delay); this.reconnect.unref?.();
      }
    });
  }

  subscribeFlow(candidates) {
    const pairs = candidates.map(r => r.pair).sort();
    if (JSON.stringify(pairs) === JSON.stringify(this.detailPairs)) return;
    this.detailSocket?.close(); this.detailPairs = pairs;
    for (const pair of this.flow.keys()) if (!pairs.includes(pair)) { this.flow.delete(pair); this.tradeIds.delete(pair); }
    if (!pairs.length) return;
    const streams = pairs.map(p => `${encodeURIComponent(p.toLowerCase())}@aggTrade`).join('/');
    const socket = new this.WebSocket(`wss://data-stream.binance.vision/stream?streams=${streams}`, { handshakeTimeout: 12_000 });
    this.detailSocket = socket;
    socket.on('error', () => {});
    socket.on('message', data => {
      try {
        const row = JSON.parse(String(data)).data, now = this.clock();
        if (row?.e !== 'aggTrade' || !pairs.includes(row.s) || typeof row.m !== 'boolean'
          || !Number.isFinite(row.T) || row.T > now || now-row.T > 30_000 || !Number.isSafeInteger(row.a)) return;
        const previousId = this.tradeIds.get(row.s);
        if (previousId !== undefined && row.a <= previousId) return;
        const size = Number(row.q); if (!(size > 0) || !Number.isFinite(size)) return;
        const history = (previousId !== undefined && row.a !== previousId+1 ? [] : this.flow.get(row.s) || []).filter(x => now-x.time <= MINUTE);
        history.push({ time: row.T, size, signed: row.m ? -size : size });
        this.tradeIds.set(row.s, row.a);
        this.flow.set(row.s, history.slice(-10_000));
      } catch { /* Malformed/untrusted messages cannot enter features. */ }
    });
    socket.on('close', () => { if (this.detailSocket === socket) { this.detailSocket = null; this.detailPairs = []; } });
  }

  async refreshDirectory() {
    if (this.sources.includes('binance') && this.clock()-this.universe.directoryAt > 24*3_600_000) {
      this.universe.setDirectory(await this.budget.json(`${BINANCE}/api/v3/exchangeInfo`), this.clock());
    }
  }

  async fallbackCoinbase() {
    if (!this.sources.includes('coinbase')) return [];
    if (this.clock()-this.coinbaseAt > 24*3_600_000) {
      const payload = await this.budget.json(`${COINBASE}/products`);
      if (!Array.isArray(payload)) throw new Error('coinbase_directory_unavailable');
      this.coinbaseProducts = payload.filter(r => r.quote_currency === 'USD' && r.status === 'online' && r.trading_disabled !== true);
      this.coinbaseAt = this.clock();
    }
    const result = [];
    for (let i = 0; i < Math.min(2, this.coinbaseProducts.length); i++) {
      const product = this.coinbaseProducts[this.coinbaseCursor++ % this.coinbaseProducts.length];
      const ticker = await this.budget.json(`${COINBASE}/products/${encodeURIComponent(product.id)}/ticker`);
      const observedAt = Date.parse(ticker.time || '');
      if (!Number.isFinite(observedAt) || this.clock()-observedAt < 0 || this.clock()-observedAt > 30_000) continue;
      result.push({ provider: 'coinbase', pair: product.id, instrument: `coinbase:spot:${product.id}`, observedAt,
        reason: 'bounded_fallback_rotation', movementBeforeAlert: null, base: product.base_currency, quote: 'USD' });
    }
    return result;
  }

  async emergingResearch() {
    if (!this.dexEnabled || this.clock()-this.dexAt < 15*MINUTE) return [];
    const profiles = await this.budget.json('https://api.dexscreener.com/token-profiles/latest/v1');
    this.dexAt = this.clock();
    const result = [];
    for (const profile of (Array.isArray(profiles) ? profiles : []).slice(0, 2)) {
      if (!/^[a-z0-9-]{1,30}$/.test(profile.chainId || '') || !/^[A-Za-z0-9]{10,100}$/.test(profile.tokenAddress || '')) continue;
      const pairs = await this.budget.json(`https://api.dexscreener.com/token-pairs/v1/${profile.chainId}/${profile.tokenAddress}`);
      for (const pair of (Array.isArray(pairs) ? pairs : []).slice(0, 5)) result.push(dexPairObservation(pair, this.clock()));
    }
    return result;
  }

  async tick() {
    const started = performance.now(), failures = [];
    try { await this.refreshDirectory(); this.connectStream(); } catch (error) { failures.push(`primary_directory_unavailable:${reasonCode(error)}`); }
    let candidates = this.universe.candidates(this.clock(), this.maxCandidates).map(r => ({ ...r, provider: 'binance' }));
    this.subscribeFlow(candidates.filter(r => r.provider === 'binance'));
    if (!candidates.length) {
      try { candidates = await this.fallbackCoinbase(); } catch { failures.push('fallback_provider_unavailable'); }
    }
    this.coverage = { ...this.universe.diagnostics(this.clock()), selected: candidates.length,
      fallbackDirectory: this.coinbaseProducts.length, fallbackScope: 'bounded two-pair rotation, not comprehensive real-time fallback', stream: this.streamStatus };
    // Exact source hints are persisted; a production bridge must independently map them.
    await writeMarketSnapshot('forecast-discovery-queue', { fetchedAt: new Date(this.clock()).toISOString(), candidates, coverage: this.coverage });
    let forecasted = 0, abstained = 0;
    const historyCache = new Map();
    const historyFor = async (provider, pair) => {
      const key = `${provider}:${pair}`;
      if (historyCache.has(key)) return historyCache.get(key);
      const raw = provider === 'binance'
        ? await this.budget.json(`${BINANCE}/api/v3/klines?symbol=${encodeURIComponent(pair)}&interval=1m&limit=1000`)
        : await this.budget.json(`${COINBASE}/products/${encodeURIComponent(pair)}/candles?granularity=60`);
      const value = provider === 'binance' ? binanceMinuteBars(raw, this.clock()) : coinbaseMinuteBars(raw, this.clock());
      historyCache.set(key, value); return value;
    };
    for (const candidate of candidates) {
      try {
        const bars = await historyFor(candidate.provider, candidate.pair);
        const benchmarks = {};
        for (const [name, base] of [['btc', 'BTC'], ['eth', 'ETH']]) {
          const pair = candidate.provider === 'binance' ? `${base}${candidate.quote}` : `${base}-USD`;
          try { benchmarks[name] = { provider: candidate.provider, pair, bars: await historyFor(candidate.provider, pair) }; }
          catch { failures.push(`benchmark_unavailable:${candidate.provider}:${pair}`); }
        }
        const flows = (this.flow.get(candidate.pair) || []).filter(r => this.clock()-r.time <= MINUTE);
        const totalFlow = flows.reduce((s, r) => s+r.size, 0);
        const coverageMs = flows.length ? flows.at(-1).time-flows[0].time : 0;
        const auxiliary = totalFlow > 0 && coverageMs >= 30_000 ? { flow_imbalance: { value: flows.reduce((s, r) => s+r.signed, 0)/totalFlow, observedAt: flows.at(-1).time, coverageMs } } : {};
        const result = await this.client.forecast({ instrument: candidate.instrument, provider: candidate.provider, pair: candidate.pair,
          sourceObservedAt: candidate.provider === 'binance' ? this.universe.observations.get(candidate.pair)?.observedAt : candidate.observedAt,
          bars, auxiliary, benchmarks, movementBeforeAlert: candidate.movementBeforeAlert,
          researchCostBps: 40, independentConfirmation: 'unverified; existing production confirmation remains mandatory' });
        forecasted++; abstained += result.forecasts.filter(r => r.abstain).length;
        this.universe.markAnalyzed(candidate.pair, this.clock());
        if (this.onForecast) {
          try { await this.deliver(candidate, result); }
          catch { failures.push(`research_delivery_failed:${candidate.instrument}`); }
        }
      } catch (error) { failures.push(`forecast_unavailable:${candidate.instrument}:${reasonCode(error)}`); }
    }
    let emerging = [];
    try { emerging = await this.emergingResearch(); } catch { failures.push('emerging_provider_unavailable'); }
    const report = { observedAt: this.clock(), coverage: this.coverage, forecasted, abstained, failures, emerging,
      providerUsage: this.budget.diagnostics(), durationMs: performance.now()-started,
      status: forecasted ? 'research_collecting' : failures.length ? 'data_or_worker_unavailable' : 'warming_up', liveTradingEnabled: false };
    await writeMarketSnapshot('forecast-worker-diagnostics', report);
    return report;
  }

  async deliver(candidate, result) {
    const state = await readMarketSnapshot('forecast-alert-delivery') || { delivered: {}, lastByInstrument: {} };
    const key = alertKey(candidate.instrument, 'experimental', this.clock());
    const previous = state.lastByInstrument?.[candidate.instrument];
    if (state.delivered[key] || previous && this.clock()-previous < 30*MINUTE) return;
    // Caller sends only to an explicitly enabled private research destination.
    await this.onForecast(forecastEmbed(result, this.coverage), key);
    state.delivered = Object.fromEntries(Object.entries({ ...state.delivered, [key]: this.clock() }).filter(([, at]) => this.clock()-at < 86_400_000));
    state.lastByInstrument = Object.fromEntries(Object.entries({ ...state.lastByInstrument, [candidate.instrument]: this.clock() }).filter(([, at]) => this.clock()-at < 86_400_000));
    await writeMarketSnapshot('forecast-alert-delivery', state);
  }

  stop() { this.stopped = true; clearTimeout(this.reconnect); this.socket?.close(); this.detailSocket?.close(); }
}
