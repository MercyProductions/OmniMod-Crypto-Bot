import test from 'node:test';
import assert from 'node:assert/strict';
import { ActivityUniverse, dexPairObservation } from '../src/forecasting/activityUniverse.js';
import { eligibleForecastDiscoveryAssets, mergeForecastDiscoveryCandidates } from '../src/forecasting/candidateBridge.js';
import { ForecastClient, forecastEmbed, alertKey, boundedJson } from '../src/forecasting/forecastClient.js';
import { PublicRequestBudget, binanceMinuteBars, coinbaseMinuteBars } from '../src/forecasting/researchWorker.js';
import { RealtimeMarketHub, parseCoinbaseMessage } from '../src/realtimeFeeds.js';
import { mkdtemp, mkdir, readFile, writeFile, copyFile, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { spawnSync } from 'node:child_process';

const now = 1_800_000_000_000;
const directory = { symbols: [{ symbol: 'QUIETUSDT', baseAsset: 'QUIET', quoteAsset: 'USDT', status: 'TRADING', isSpotTradingAllowed: true }] };

test('legacy realtime consensus cannot turn a delayed tick into fresh confirmation on receipt', () => {
  const hub = new RealtimeMarketHub({ enabled: false });
  const quote = { provider: 'Coinbase WS', symbol: 'BTC', price: 100, timestampBasis: 'provider_event' };
  for (const stamp of [Date.now()-120_000, Date.now()+120_000]) {
    hub.recordQuote({ ...quote, providerObservedAt: new Date(stamp).toISOString() });
    assert.equal(hub.getConsensus('BTC').providerCount, 0);
  }
  hub.recordQuote({ ...quote, providerObservedAt: new Date().toISOString() });
  assert.equal(hub.getConsensus('BTC').providerCount, 1);
  assert.ok(parseCoinbaseMessage({ type: 'ticker', product_id: 'BTC-USD', price: 100, time: new Date().toISOString() }).providerObservedAt);
  hub.stop();
});

test('quiet liquid pairs enter discovery without a positive 24h move', () => {
  const universe = new ActivityUniverse(); universe.setDirectory(directory, now);
  universe.observe({ s: 'QUIETUSDT', E: now-1000, c: '10', q: '2000000' }, now);
  const result = universe.candidates(now);
  assert.equal(result.length, 1); assert.equal(result[0].stage, 'EARLY WATCH');
  assert.equal(result[0].activityIsProbability, false); assert.equal(result[0].reason, 'liquid_universe_rotation');
});

test('valid Unicode venue symbols do not invalidate the entire active directory', () => {
  const universe = new ActivityUniverse();
  universe.setDirectory({ symbols: [...directory.symbols, { ...directory.symbols[0], symbol: '币安人生USDT', baseAsset: '币安人生' }] }, now);
  universe.observe({ s: '币安人生USDT', E: now, c: '1', q: '2000000' }, now);
  assert.equal(universe.directory.size, 2); assert.equal(universe.candidates(now).length, 1);
});

test('native event times reject stale/future/replayed frames and inactive universe refresh removes pairs', () => {
  const universe = new ActivityUniverse(); universe.setDirectory(directory, now);
  for (const E of [now+1, now-60_000, undefined]) assert.equal(universe.observe({ s: 'QUIETUSDT', E, c: '10', q: '2000000' }, now), false);
  assert.equal(universe.observe({ s: 'QUIETUSDT', E: now, c: '10', q: '2000000' }, now), true);
  assert.equal(universe.observe({ s: 'QUIETUSDT', E: now, c: '10', q: '2000000' }, now), false);
  universe.setDirectory({ symbols: [{ ...directory.symbols[0], status: 'BREAK' }] }, now);
  assert.equal(universe.candidates(now).length, 0);
});

test('turnover proxy before price expansion is distinguished from an already completed large move', () => {
  const universe = new ActivityUniverse(); universe.setDirectory(directory, now-60_000);
  universe.observe({ s: 'QUIETUSDT', E: now-60_000, c: '10', q: '2000000' }, now-60_000);
  universe.observe({ s: 'QUIETUSDT', E: now, c: '10.01', q: '2040000' }, now);
  assert.equal(universe.candidates(now)[0].reason, 'turnover_change_before_price_expansion');
  universe.observe({ s: 'QUIETUSDT', E: now+15_000, c: '12', q: '2040000' }, now+15_000);
  assert.equal(universe.candidates(now+15_000)[0].alreadyExpanded, true);
});

test('forecast bridge requires existing unique exact venue/CoinGecko identity, never ticker-only guesses', () => {
  const asset = { id: 'quiet-coin', requiresVerifiedIdentity: true, venueDiscovery: { coinId: 'quiet-coin', exchangeId: 'binance', base: 'QUIET', target: 'USDT' } };
  const hint = { instrument: 'binance:spot:QUIETUSDT', pair: 'QUIETUSDT', base: 'QUIET', quote: 'USDT', observedAt: now };
  assert.equal(eligibleForecastDiscoveryAssets([hint], [asset], now).assets.length, 1);
  assert.equal(eligibleForecastDiscoveryAssets([{ ...hint, quote: 'BTC' }], [asset], now).assets.length, 0);
  assert.equal(eligibleForecastDiscoveryAssets([hint], [asset, { ...asset, id: 'different', venueDiscovery: { ...asset.venueDiscovery, coinId: 'different' } }], now).assets.length, 0);
  assert.equal(eligibleForecastDiscoveryAssets([{ ...hint, observedAt: now-60_000 }], [asset], now).assets.length, 0);
});

test('discovery gets a bounded detail slot without increasing the request budget', () => {
  const existing = [{ id: 'a' }, { id: 'b' }], hint = { id: 'c' };
  assert.deepEqual(mergeForecastDiscoveryCandidates(existing, [hint], 2), [existing[0], hint]);
  assert.deepEqual(mergeForecastDiscoveryCandidates(existing, [], 2), existing);
});

test('DEX identities remain chain/contract-specific and missing native timestamps cannot become forecasts', () => {
  const row = dexPairObservation({ chainId: 'solana', pairAddress: 'pair', baseToken: { address: 'contract', symbol: 'BTC' }, priceUsd: '1', liquidity: { usd: 30000 } }, now);
  assert.equal(row.eligibleForForecast, false); assert.equal(row.providerObservedAt, null);
  assert.notEqual(row.instrument, 'binance:spot:BTCUSDT');
});

test('local budgets and HTTP 429 cooldown stop requests instead of retry storms', async () => {
  let calls = 0;
  const budget = new PublicRequestBudget({ clock: () => now, fetchImpl: async () => { calls++; return new Response('{}', { status: 429, headers: { 'retry-after': '120' } }); } });
  await assert.rejects(budget.json('https://example.invalid/one'), /429/);
  await assert.rejects(budget.json('https://example.invalid/two'), /cooldown/);
  assert.equal(calls, 1);
});

test('incomplete candle exclusion and exact units apply to both free providers', () => {
  const stamp = Math.floor(now/60_000)*60_000;
  assert.equal(binanceMinuteBars([[stamp, 1, 2, 1, 2, 3, 0, 5, 4, 1]], now).length, 0);
  const rows = coinbaseMinuteBars([[(stamp-60_000)/1000, 1, 2, 1, 2, 3]], now);
  assert.equal(rows[0].time, stamp-60_000);
});

test('authenticated client forbids insecure remote URLs and rejects production approval in research responses', async () => {
  assert.throws(() => new ForecastClient({ url: 'http://example.com', token: 'x'.repeat(32) }), /https_or_loopback/);
  const client = new ForecastClient({ token: 'fixture-token-for-tests-only-00000000', fetchImpl: async () => new Response(JSON.stringify({ instrument: 'p', liveTradingEnabled: false, productionApproval: true, forecasts: [] })) });
  await assert.rejects(client.forecast({ instrument: 'p' }), /invalid_forecast_response/);
});

test('streamed responses without length headers still obey the memory bound', async () => {
  await assert.rejects(boundedJson(new Response('x'.repeat(100)), 20), /response_size_limit/);
});

test('local token initializer preserves adjacent settings and never prints the generated secret', async t => {
  const folder = await mkdtemp(join(tmpdir(), 'crypto-forecast-token-'));
  t.after(async () => { assert.ok(folder.startsWith(join(tmpdir(), 'crypto-forecast-token-'))); await rm(folder, { recursive: true, force: true }); });
  await mkdir(join(folder, 'scripts'));
  const script = join(folder, 'scripts', 'setup-forecast-token.mjs');
  await copyFile(new URL('../scripts/setup-forecast-token.mjs', import.meta.url), script);
  await writeFile(join(folder, '.env'), 'CRYPTO_FORECAST_TOKEN=\nDISCORD_CLIENT_ID=fixture-id\n');
  const run = spawnSync(process.execPath, [script], { encoding: 'utf8' });
  assert.equal(run.status, 0);
  const content = await readFile(join(folder, '.env'), 'utf8');
  const secret = content.match(/^CRYPTO_FORECAST_TOKEN=(.*)$/m)[1];
  assert.equal(secret.length, 96); assert.ok(content.includes('DISCORD_CLIENT_ID=fixture-id'));
  assert.ok(!run.stdout.includes(secret));
  assert.equal(spawnSync(process.execPath, [script]).status, 0);
  assert.equal(await readFile(join(folder, '.env'), 'utf8'), content);
});

test('Discord embed preserves experimental/price labels and delivery keys deduplicate a research window', () => {
  const result = { instrument: 'binance:spot:BTCUSDT', forecasts: [{ model: 'none', modelVersion: 'fixture', abstain: true, issuedAt: now,
    forecastExpiresAt: now+60_000, referencePrice: 10, reason: 'no validated model', expectedReturn: null }] };
  const embed = forecastEmbed(result, { freshObserved: 1000, activeSpot: 2000 });
  assert.match(embed.description, /EARLY WATCH/); assert.match(embed.description, /subset/);
  assert.match(embed.fields.find(f => f.name === 'Price and timing').value, /not an executable quote/);
  assert.equal(alertKey('p', 'watch', now), alertKey('p', 'watch', now+1000));
  result.forecasts[0].movementBeforeAlert = .12;
  assert.match(forecastEmbed(result).description, /POST-MOVE RESEARCH/);
});
