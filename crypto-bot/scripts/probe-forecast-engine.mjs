import 'dotenv/config';
import { ForecastResearchWorker } from '../src/forecasting/researchWorker.js';

// Explicit, bounded public-provider probe. No Discord, paper reservation or orders.
const worker = new ForecastResearchWorker({ token: process.env.CRYPTO_FORECAST_TOKEN,
  url: process.env.CRYPTO_FORECAST_URL || 'http://127.0.0.1:8765', maxCandidates: 2 });
try {
  const first = await worker.tick();
  await new Promise(resolve => setTimeout(resolve, 15_000));
  const second = await worker.tick();
  console.log(JSON.stringify({ mode: 'bounded_public_research_probe', passes: [first, second],
    discordDeliveryExercised: false, productionApproval: false, liveTradingEnabled: false }));
} finally { worker.stop(); }
