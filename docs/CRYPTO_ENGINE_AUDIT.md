# Crypto forecasting engine: audit and evidence

Audit baseline: `9b88a9f2028a4dcb5d37bfa505378c065335ed72`, preserved as `baseline/pre-crypto-forecasting-2026-10-20` and a private local Git bundle. Baseline: **392 tests passed** after locked dependency bootstrap. The initial clean checkout lacked dependencies; that first missing-dotenv run was an environment failure, not a strategy failure.

## Existing lifecycle and scope

The repository deliberately includes the shared six-market bundle. Crypto is `crypto-bot/`; the root wrapper launches only that bot. Its 70 source modules contain 12,298 lines. All 70 baseline source files matched the original local source folder byte-for-byte. This does **not** attest what is running on cPanel; no remote process/hash inspection or credential change was performed.

`cryptoData.fetchMarketUniverse` fetches volume/capitalization pages, rotating broad discovery and venue metadata. `screenMomentumDetailed` applies freshness, identity, rank/liquidity, score and trend filters. `index.executeGuildScan` caps expensive work, verifies pair coverage and enriches assets through `marketProviders.enrichMarketAssets`. That fetches exact-source history, technicals, BTC context, quotes, books, derivatives and event risks. `predictionEngine` creates a conditional paper setup; portfolio, rolling risk guard and shared paper-execution checks remain distinct. Discord publication and paper fills/outcomes are separate events. `researchStore` freezes source-pinned shadow observations and resolves only supported outcomes. `metaModel`, `outcomeModels` and `modelRegistry` train and gate actual boosted-stump/regression candidates. `backtest` and `historicalBacktest` already enforce completed candles, conservative stop-first ambiguity, next-open simulation, chronology and costs.

## Confirmed bottlenecks / limitations

| Component | Observed fact | Consequence / repair direction |
| --- | --- | --- |
| `broadDiscovery.planBroadDiscovery` | 50-ID / 1,500-character public batch envelope; normal discovery cadence 15 minutes. | A 21,000-asset directory requires 420 batches, about 105 hours at that cadence. This is arithmetic, not a new live coverage measurement. Retain metadata rotation but do not use it as the intraday price sweep. |
| `venueDiscovery.screenBinanceBulk` | Bulk activity ranking requires positive 24h change and favors larger completed movement. | Useful momentum research baseline, not accumulation detection. Add a separate rolling activity queue without relaxing production entry gates. |
| `index.executeGuildScan` / `realtimeFeeds.start` | Live subscriptions begin after momentum/pair screening and stop at 20 symbols. | Quiet assets can never accumulate early live evidence. Separate broad streaming discovery from a bounded detailed feed pool. |
| `realtimeFeeds.recordQuote` | Consensus age uses local receipt time; Binance/Coinbase parsers do not retain native event time. | Delayed/replayed ticks can look newly observed. The new research path must enforce native timestamps and exact venue/pair identities. |
| `modelRegistry` | Model activation requires corrected source/entry/outcome schemas, enough labels, validation-day coverage and cost stress. | Cold-start inactivity is intentional. Train challengers independently; never relabel a heuristic score as calibrated probability. |
| `metaModel.trainBoostedModel` | Real boosted stumps and purged folds exist; the blind segment also supplies conformal calibration. | Raw-model blind metrics do not independently validate the fitted conformal set. New pipeline needs separate calibration and final holdout; existing calibrated claims need that limitation. |
| `outcomeModels.trainValidatedRegression` | Residual intervals are fitted from the same blind residuals used to accept the regressor; baseline MAE uses the test-target mean. | Interval coverage is not untouched validation; the oracle-centered reference is not a deployable mean forecast. Preserve baseline behavior for comparison, use training-only references and separate calibration in the challenger path. |
| `venueResearch` | Source-pinned pending outcomes are capped at two pulls per pass and recent-history coverage. | Old/large backlogs can stay unresolved; missing outcomes are not wins/losses. New forecast store must expose pending/censored counts. |
| Existing history | Public OHLCV does not reconstruct old L2 books, revisions, identity mapping or executable fills. | Missing microstructure stays null. No synthetic order-flow history, real-fill claim or survivorship-free claim. |
| Deployment | GitHub/local matching source is known; hosting RAM/Python/provider permissions are not verified. | Keep inference in an isolated local/remote worker with bounded requests, authentication and fail-closed behavior. No assumed cPanel ML capacity. |

## Architecture decision

Preserve the current model and paper execution as the production baseline. Add an opt-in research pipeline: venue-wide cheap activity observations → exact-identity candidate queue → bounded history/microstructure collection → timestamped feature/forecast warehouse → Python LightGBM / Chronos challengers → experimental Discord embeds and frozen outcome grading. The production scanner may consume only independently identity-verified research candidates through its existing checks. New research alone never reserves a paper order or bypasses the emergency stop.

Use 5/15/60/240/1440-minute targets with separate task/horizon records. Training, tuning, calibration and final holdout are time-separated with label-end purging/embargo across all assets. Missing bid/ask costs forbid an actionable EV claim. The holdout is not a repeated model-selection pool. Automatic deployment requires prospective matched evidence; historical success alone remains research.

## Source and license references

- [Binance public archives](https://github.com/binance/binance-public-data): spot archives changed to microsecond timestamps in 2025; verify SHA-256 sidecars and retain provenance. Data terms apply independently of open-source code.
- [Binance stream specification](https://github.com/binance/binance-spot-api-docs/blob/master/web-socket-streams.md): respect access controls, subscription/message limits and reconnect rules. No regional circumvention.
- [LightGBM](https://github.com/lightgbm-org/LightGBM): MIT-licensed training/inference candidate, not a trading strategy by itself.
- [Chronos code](https://github.com/amazon-science/chronos-forecasting) and [Bolt Tiny model card](https://huggingface.co/amazon/chronos-bolt-tiny): Apache-2.0; preserve notices and pin model revision. Pretraining overlap with crypto archives is unknown; historical zero-shot results cannot prove independent out-of-sample skill.
- [DEX Screener API](https://docs.dexscreener.com/api/reference) and [terms](https://docs.dexscreener.com/api/api-terms-and-conditions): rate-limited emerging-pair research, not exhaustive coverage or a recommendation to buy promoted tokens.
- Existing `protocolFundamentals.js` already integrates DeFiLlama context separately from intraday approval. TVL is price-sensitive; data licensing/redistribution and paid entitlements remain separate decisions.

Implementation results, measured model scores and operational limitations are recorded in the phase checklist and subsequent experiment reports. No production change or profitability claim follows from this audit.
