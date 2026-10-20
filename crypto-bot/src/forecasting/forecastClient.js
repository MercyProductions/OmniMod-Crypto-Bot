import { createHash } from 'node:crypto';

export async function boundedJson(response, limit = 2_000_000) {
  if (Number(response.headers?.get('content-length')) > limit) throw new Error('response_size_limit');
  const reader = response.body.getReader(); const chunks = []; let size = 0;
  try {
    while (true) {
      const { done, value } = await reader.read(); if (done) break;
      size += value.length;
      if (size > limit) { await reader.cancel(); throw new Error('response_size_limit'); }
      chunks.push(Buffer.from(value));
    }
  } finally { reader.releaseLock(); }
  return JSON.parse(Buffer.concat(chunks).toString('utf8'));
}

export class ForecastClient {
  constructor({ url = 'http://127.0.0.1:8765', token, timeoutMs = 15_000, fetchImpl = fetch } = {}) {
    const endpoint = new URL(url);
    if (endpoint.username || endpoint.password || endpoint.search || endpoint.hash
      || !(endpoint.protocol === 'https:' || endpoint.protocol === 'http:' && ['127.0.0.1', 'localhost', '[::1]'].includes(endpoint.hostname))) throw new Error('forecast_worker_requires_https_or_loopback');
    if (!token || token.length < 32) throw new Error('private_forecast_token_required');
    this.url = endpoint.origin; this.token = token; this.timeoutMs = timeoutMs; this.fetch = fetchImpl;
  }
  async forecast(payload) {
    const body = JSON.stringify(payload);
    if (Buffer.byteLength(body) > 2_000_000) throw new Error('forecast_body_limit');
    const response = await this.fetch(`${this.url}/v1/forecast`, { method: 'POST', redirect: 'error',
      signal: AbortSignal.timeout(this.timeoutMs), headers: { 'content-type': 'application/json', authorization: `Bearer ${this.token}` }, body });
    if (!response.ok) {
      const detail = await boundedJson(response).catch(() => ({}));
      const reason = /^[a-z_]{1,80}$/.test(detail.reason || '') ? `:${detail.reason}` : '';
      throw new Error(`forecast_worker_http_${response.status}${reason}`);
    }
    if (Number(response.headers?.get('content-length')) > 2_000_000) throw new Error('forecast_response_limit');
    const result = await boundedJson(response);
    if (result.instrument !== payload.instrument || result.liveTradingEnabled !== false || result.productionApproval !== false || !Array.isArray(result.forecasts)) throw new Error('invalid_forecast_response');
    return result;
  }
}

export function forecastEmbed(result, coverage = {}) {
  const forecasts = (result.forecasts || []).filter(r => !r.abstain && Number.isFinite(r.expectedReturn));
  const leading = forecasts.find(r => r.model === 'LightGBM' && r.horizonMinutes === 60) || forecasts[0];
  const sample = leading || result.forecasts?.[0];
  if (!sample) throw new Error('empty_forecast');
  const text = value => String(value ?? 'Unavailable').slice(0, 900);
  const expanded = Math.abs(sample.movementBeforeAlert || 0) >= .01;
  return { color: 0x7289da, title: 'OmniMod Crypto · Experimental forecast research',
    description: `${result.instrument}\n${expanded ? 'POST-MOVE RESEARCH — price has already expanded' : leading ? 'EXPERIMENTAL FORECAST' : 'EARLY WATCH — model abstained'}\nHighlights are a subset of monitored markets. No validated opportunity or paper entry is implied.`,
    fields: [
      { name: 'Coverage', value: text(`${coverage.freshObserved ?? 'unknown'} fresh / ${coverage.activeSpot ?? 'unknown'} active venue pairs; selected detail ${coverage.selected ?? 'unknown'}.`) },
      { name: 'Forecast', value: leading ? `${leading.expectedReturn > 0 ? 'Upward' : 'Downward/flat'} research estimate; ${leading.horizonMinutes} minutes. Experimental probabilities are not calibrated production confidence.` : text(sample.reason) },
      { name: 'Expected return range', value: leading?.returnRange ? text(leading.returnRange.map(x => `${(x*100).toFixed(2)}%`).join(' to ')) : 'Unavailable; no range invented.' },
      { name: 'After-cost context', value: Number.isFinite(sample.expectedReturnAfterResearchCosts) ? `${(sample.expectedReturnAfterResearchCosts*100).toFixed(2)}% after the stated ${sample.costBps} bps OHLC research assumption. Actual spread, slippage, depth and EV remain unverified.` : 'Unavailable; no executable EV or profit claim.' },
      { name: 'Supporting evidence', value: sample.supportingEvidence?.length ? text(sample.supportingEvidence.slice(0, 4).map(r => `${r.feature}: ${Number(r.value).toPrecision(3)} (model contribution ${Number(r.logitContribution).toFixed(3)})`).join('\n')+'\nModel associations, not causal proof.') : 'Insufficient trained evidence; no rationale invented.' },
      { name: 'Regime / data quality', value: text(`${sample.marketRegime || 'unclassified'}; fresh completed candles. Independent executable-quote confirmation remains required.`) },
      { name: 'Price and timing', value: `${text(sample.referencePrice)} · last completed close, not an executable quote.\nIssued <t:${Math.floor(sample.issuedAt/1000)}:T>; expires <t:${Math.floor(sample.forecastExpiresAt/1000)}:T>.` },
      { name: 'Movement already observed', value: Number.isFinite(sample.movementBeforeAlert) ? `${(sample.movementBeforeAlert*100).toFixed(2)}% in the worker observation window; this is not predicted profit.` : 'Unknown; no early lead-time claim.' },
      { name: 'Entry / invalidation', value: 'Fresh executable quote, independent confirmation, validated model and all existing EV/risk gates are still required. Stale data, conflicts or expiry invalidate this research watch.' },
      { name: 'Model and evidence', value: text(`${sample.model} · ${sample.modelVersion}. ${sample.reason || ''}`) }
    ], footer: { text: 'Research only · live trading disabled · no order placed' } };
}

export function alertKey(instrument, stage, now = Date.now(), cooldownMs = 30*60_000) {
  return createHash('sha256').update(`${instrument}|${stage}|${Math.floor(now/cooldownMs)}`).digest('hex').slice(0, 24);
}
