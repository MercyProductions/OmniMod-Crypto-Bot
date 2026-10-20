import 'dotenv/config';
import { ForecastResearchWorker } from '../src/forecasting/researchWorker.js';
import { dataDir } from '../src/config.js';
import { join } from 'node:path';
import { acquireMarketApplicationLock } from '../../new-bots/shared/marketBotRuntime.js';

if (process.env.CRYPTO_FORECAST_ENABLED !== 'true') throw new Error('Explicitly set CRYPTO_FORECAST_ENABLED=true for this isolated research worker.');
const discordEnabled = process.env.CRYPTO_FORECAST_DISCORD_ENABLED === 'true';
let onForecast = null;
if (discordEnabled) {
  const channel = process.env.CRYPTO_FORECAST_RESEARCH_CHANNEL_ID || '';
  const token = process.env.DISCORD_TOKEN || '';
  if (!/^\d{16,22}$/.test(channel) || !token) throw new Error('Own Discord token and explicit private research channel required.');
  onForecast = async (embed, key) => {
    const response = await fetch(`https://discord.com/api/v10/channels/${channel}/messages`, {
      method: 'POST', signal: AbortSignal.timeout(10_000), headers: { authorization: `Bot ${token}`, 'content-type': 'application/json' },
      body: JSON.stringify({ embeds: [embed], allowed_mentions: { parse: [] }, nonce: key, enforce_nonce: true }) });
    if (!response.ok) throw new Error(`research_discord_http_${response.status}`);
  };
}
const worker = new ForecastResearchWorker({ token: process.env.CRYPTO_FORECAST_TOKEN,
  url: process.env.CRYPTO_FORECAST_URL || 'http://127.0.0.1:8765',
  sources: (process.env.CRYPTO_FORECAST_SOURCES || 'binance,coinbase').split(',').map(s => s.trim()),
  maxCandidates: Number(process.env.CRYPTO_FORECAST_MAX_CANDIDATES) || 6,
  dexEnabled: process.env.CRYPTO_FORECAST_DEX_ENABLED === 'true', onForecast });
const requestedInterval = Number(process.env.CRYPTO_FORECAST_INTERVAL_SECONDS);
const intervalSeconds = Number.isFinite(requestedInterval) ? Math.max(60, Math.min(3600, requestedInterval)) : 60;
let stopping = false;
let wake = null;
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => { stopping = true; worker.stop(); wake?.(); });
const release = await acquireMarketApplicationLock(join(dataDir, 'forecast-research'), 'crypto-forecast-research');
try { while (!stopping) {
  try { const report = await worker.tick(); console.log(JSON.stringify(report)); }
  catch { console.error('Forecast research pass unavailable; no production approval or order created.'); }
  if (process.argv.includes('--once')) break;
  await new Promise(resolve => {
    const timer = setTimeout(resolve, intervalSeconds*1000);
    wake = () => { clearTimeout(timer); resolve(); };
  });
} } finally { worker.stop(); await release(); }
