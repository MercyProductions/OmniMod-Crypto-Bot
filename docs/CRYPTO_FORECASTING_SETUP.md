# Crypto forecasting research: developer setup and handoff

This is an **opt-in development/research pipeline**, alongside the existing Crypto Discord bot. It does not enable live orders, replace the old production model or turn experimental scores into approved entries. Preserve `baseline/pre-crypto-forecasting-2026-10-20`, private runtime backups and each experiment directory. Read the [audit](CRYPTO_ENGINE_AUDIT.md), [measured experiment](CRYPTO_ENGINE_RESULTS.md) and [phase checklist](CRYPTO_ENGINE_PHASES.json).

## Components and data flow

| Component | Responsibility |
| --- | --- |
| `crypto-bot/src/forecasting/activityUniverse.js` | Active venue directory, native timestamp validation, bounded rolling activity history and fair rotation. Does not require a positive 24h return. |
| `researchWorker.js` | One Binance aggregate mini-ticker stream; bounded selected-pair trade streams; cached benchmark histories; exact-pair candle pulls, Coinbase fallback and optional DEX research. |
| `candidateBridge.js` | Optional one-slot bridge into the old analyzer, only for existing unique CoinGecko/venue identity mappings. Final score, model, quote, event, correlation and risk checks remain. |
| `forecastClient.js` | Authenticated bounded Node→Python requests and clearly experimental Discord embeds. |
| `forecasting/engine/features.py` | Causal one-minute OHLCV, flow and technical features, exact-time BTC/ETH context, horizon labels and conservative stop-first outcomes. |
| `archive.py` / `cli.py` | Checksum-verified official archive import; isolated training from archives **or** completed prospective warehouse observations. |
| `models.py` / `validation.py` | Real native LightGBM tasks, pinned optional Chronos, global chronological cuts, purge/embargo, separate calibration, proper scores and reference comparisons. |
| `warehouse.py` | Private SQLite WAL store: immutable bars, features, forecasts, linked outcomes and frozen no-change references. |
| `registry.py` | Matched prospective research review; suspend deteriorating research models and revert to abstention. Never authorizes production trading. |
| `service.py` | Loopback-only authenticated inference service; single inference capacity, body/response limits and safe failure. |

Keep research state separate from production state. The optional bridge reads `forecast-discovery-queue` from the same **absolute** `OMNIMOD_CRYPTO_DATA_DIR` as the Discord bot only when explicitly enabled. If you intentionally use separate directories, the bridge will not see that queue. The Python SQLite path is independently explicit; persist it outside replaceable deployment source.

## Install

From the repository root, run `npm run bootstrap` to install the existing locked Node dependencies. Use **Python 3.11+**; the tested environment was Python 3.14.3, Node 24.14.1, CPU-only PyTorch 2.14.0, 32 GB system RAM. That RAM amount is the test machine, not a measured minimum. Python 3.10 cannot satisfy the pinned scientific package requirements.

```powershell
python -m venv .venv-forecast
.\.venv-forecast\Scripts\Activate.ps1
python -m pip install -r crypto-bot/forecasting/requirements.txt
```

On Linux/macOS, activate with `source .venv-forecast/bin/activate`. `requirements.txt` is sufficient for LightGBM. For Chronos, first install a platform-compatible CPU/GPU PyTorch build, then install `requirements-chronos.txt`. No GPU is required for Bolt Tiny. Do not replace a hosting provider's system Python environment. The service must use the environment containing these libraries.

## Local credentials and defaults

Use your own `crypto-bot/.env`, following the root README. [`.env.forecasting.example`](../crypto-bot/.env.forecasting.example) lists the new settings. Copy individual values into your existing local file; do not overwrite your Discord/provider configuration with a new template.

```sh
npm --prefix crypto-bot run forecast:setup-token
```

This optional command generates a random research token in the ignored local `.env` only if one is absent/blank. It preserves existing nonblank tokens and never prints them. Run it in your own development checkout; do not change a running production credential. The Python service reads only `CRYPTO_FORECAST_TOKEN` from its current local `.env` if the process environment did not supply it. Node loads its usual local `.env`. Never put a token in a URL, command-line argument, Git issue or PR.

| Setting | Default / use |
| --- | --- |
| `CRYPTO_FORECAST_ENABLED` | `false`; explicit opt-in for the separate Node worker. |
| `CRYPTO_FORECAST_URL` | `http://127.0.0.1:8765`; non-loopback URLs must use HTTPS, without URL credentials. |
| `CRYPTO_FORECAST_TOKEN` | Your own random value, at least 32 characters; shared only by the Node client and Python service. |
| `CRYPTO_FORECAST_SOURCES` | `binance,coinbase`; keyless public collection, subject to provider availability/terms. |
| `CRYPTO_FORECAST_MAX_CANDIDATES` | 6, hard-capped at 12. This is a detail budget, not total universe size. |
| `CRYPTO_FORECAST_INTERVAL_SECONDS` | At least 60 seconds per completed pass. No concurrent passes. |
| `CRYPTO_FORECAST_DEX_ENABLED` | `false`; optional emerging-pair metadata research, not forecast/order eligibility. |
| `CRYPTO_FORECAST_DISCORD_ENABLED` | `false`; no message is sent unless enabled with your own token and explicit research channel. |
| `CRYPTO_FORECAST_RESEARCH_CHANNEL_ID` | Your private research destination. Normal production channels are not inferred. |
| `CRYPTO_FORECAST_DISCOVERY_BRIDGE_ENABLED` | `false`; opt-in behavioral change reserving one existing deep-analysis slot. Forward paper validation required. |

The existing Discord token is needed only if you enable research posting; no exchange trading key is needed. Existing CoinGecko Demo/Pro, derivatives and paid-provider options remain available through the old pipeline. A public endpoint returning 403/451 is a restriction/failure, not an invitation to bypass regional controls.

## Reproduce the bounded historical study

The following downloads six explicit pair-month archives. It is not an exhaustive/delisting-aware market sample. The importer accepts requested historical pair files without filtering against today's active directory, so valid inactive-pair histories can be studied separately. A point-in-time multi-asset master and broader failed-asset sample are still required before generalizing.

```sh
npm --prefix crypto-bot run forecast:download -- --pairs BTCUSDT ETHUSDT --months 2025-07 2025-08 2025-09 --directory datasets/binance
npm --prefix crypto-bot run forecast:train -- --directory datasets/binance --output artifacts/my-first-study --stride 30 --cost-bps 40
```

Archive SHA-256 sidecars are verified; microsecond spot timestamps are converted explicitly. An existing experiment artifact cannot be overwritten. Preserve data manifests, experiment fingerprint, parameters and package/model revisions. Inspecting the same holdout repeatedly is not additional independent evidence. The 40 bps cost is an explicit all-in research assumption, not measured venue fees/spread/slippage or the old production default.

To include the pinned Chronos challenger, append:

```text
--chronos-revision a0e552de83495b5c28c14c71c374f3e33280b340 --chronos-samples 10
```

This revision is `amazon/chronos-bolt-tiny`, Apache-2.0. Weights are downloaded separately; they and historical datasets are not shipped in Git. Initial download needs network/disk space. The adapter uses CPU inference, completed context aggregation for long horizons, and direct forecasts of at most 64 steps. Raw quantiles are not calibrated crypto probabilities. Pretraining overlap with the evaluation history is unknown.

## Run the research service and collector

Use two activated terminals. Start inside `crypto-bot/` or use npm prefix so the local `.env` is the intended one:

```sh
npm --prefix crypto-bot run forecast:service -- --database data/forecasting/warehouse.sqlite --artifact artifacts/my-first-study/lightgbm.json
```

Add the same `--chronos-revision` option if you want the optional challenger. Without an artifact the service works but abstains rather than inventing probabilities. Set `CRYPTO_FORECAST_ENABLED=true` in your local development `.env`, then:

```sh
npm --prefix crypto-bot run forecast:worker
```

For a bounded live smoke check instead of a continuous worker:

```sh
npm --prefix crypto-bot run forecast:probe
```

The probe contacts free providers and your configured inference service, waits 15 seconds, records two passes and exits. It sends no Discord messages or orders. Do not run probes beside an active collector against the same state/provider budget. The Python service owns an exclusive `<database>.service.lock`; the continuous Node worker owns an exclusive local application lock under `forecast-research/`; inspect owner/PID/host before removing a crash-left lock. It shuts down on SIGINT/SIGTERM.

Binance supplies venue-wide activity through one aggregate stream. Only changed symbols appear in each update, so a 15-second sample is not guaranteed complete coverage. A rolling 24h turnover change is labeled a proxy; it is not measured new traded volume. Selected aggregate trades supply native-timestamped aggressor flow. Coinbase fallback rotates two eligible USD products per pass; it is intentionally bounded and **not** equivalent to full-market streaming. Kraken remains available through the existing independently verified confirmation/paper quote pipeline; it is not a newly implemented universe-wide fallback in this collector.

Public requests are paced to 12/minute/host locally, with HTTP cooldowns and reported Binance weight when present. This is not a shared account-wide quota manager. Broad metadata, paid API entitlements and other processes have separate budgets. DEX Screener latest profiles/pairs are a small emerging-asset sample, with chain/contract identity; missing native timestamps prohibit their use as fresh executable forecasts. Existing DeFiLlama fundamentals stay longer-horizon context. CryptoDataDownload was not integrated because permitted redistribution/use was not established; no website scraping is added.

## Forecasts, grading and retraining

Each 5/15/60/240/1440-minute forecast freezes source instrument, features, data cutoff, native/receipt timestamps, model identity, task probabilities, expected return/range, volatility evidence, regime and expiration. TreeSHAP contributions explain model associations; they do not establish causation. Experimental probabilities remain separate from `calibratedProbability`, which stays null without prospective approval. A >=1% observed move is explicitly post-move research, not an early prediction.

`EARLY WATCH` means unusual/developing observations or abstention. New models never get labeled `PREDICTED OPPORTUNITY` or `PAPER TRADE QUALIFIED` merely by completing a request. Those labels need independent validation and the existing production approval chain. Executable bid/ask, liquidity-adjusted costs, event vetoes, correlated/shared exposure, emergency stops and paper execution remain mandatory. An estimated upward move smaller than costs is not an opportunity.

Predictions are computed from completed bars; forward OHLC research starts at the next **full** minute after recording, avoiding use of the partly elapsed entry candle. Expiration is that entry boundary plus the horizon. Missing minute windows remain unresolved. A target/stop collision is stop-first; gap stops include the adverse gap; target fills never assume extra price improvement. Outcomes record returns, target-before-stop, full-horizon OHLC excursion bounds (not executed-position MFE/MAE), event-bar timing and before/after-alert movement. Lead time is an interval bounded by the target-touch candle, not an invented exact trade time. These are simulated OHLC labels, not executable fills. An absent observation window means unknown lead time, not zero lead time. Discord delivery is not attested by the Python journal.

Train from accumulated completed research independently of the archive corpus:

```sh
npm --prefix crypto-bot run forecast:train -- --warehouse data/forecasting/warehouse.sqlite --output artifacts/forward-study-001
```

This opens the warehouse read-only, deduplicates source/input/horizon rows and preserves actual label-observation availability in purging. Archive and prospective populations are not silently pooled. There is no timer that repeatedly retrains/selects against the same holdout. Insufficient completed outcomes cannot produce an approved model.

The research registry reviews a fixed daily hash sample (up to 200 resolved rows/day over 90 days), at most every six hours when new outcomes exist. It requires post-training/staging forecasts, identical frozen inputs/cutoffs, one horizon, at least 500 samples/30 days, proper-score improvement and verified point-in-time costs before research review eligibility. Current OHLC-only costs cannot satisfy that last requirement. Supported deterioration can suspend research forecasts and revert to abstention. This does not mutate the old production registry or promote an ensemble automatically. A validated ensemble is deliberately absent until there is evidence to justify one.

## Diagnostics, durability and hosting

`forecast-worker-diagnostics` and `forecast-discovery-queue` snapshots expose observed/active/selected counts, failures, timing, request budgets and inference/abstention counts. Authenticated `GET /v1/health` returns warehouse counts/pending outcomes. Zero forecasts with source/worker failures is reported as unavailable, not an empty healthy market. Source revisions are rejected for investigation instead of silently changing frozen bars. Back up the SQLite database consistently with its WAL; do not copy only the main file while writes are active. No automatic evidence pruning is implemented; monitor storage and plan evidence-preserving archives.

cPanel's actual Python/package/RAM/process support is **unverified**. The existing Node app can remain where it is; run inference on a local machine or dedicated Python-capable host. The service binds only to loopback. For a remote Node client, use a private tunnel or authenticated TLS reverse proxy with network restrictions and body/rate limits; do not expose the raw port or reuse Discord/provider secrets as service tokens. A worker timeout, stale source, incompatible model, corrupted artifact, missing history or failed authentication yields no production approval. Do not assume published GitHub source is deployed.

Verification:

```sh
npm test
npm run check
npm --prefix crypto-bot run test:forecast-python
```

Activate the forecasting environment before the Python command. The original source baseline remains available for comparisons. See the [results](CRYPTO_ENGINE_RESULTS.md) for measured performance, failure cases and work that remains unverified.
