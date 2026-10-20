# Crypto engine upgrade: measured results and limits

## Status

Working development implementation: separate Node discovery/collector, authenticated Python inference, actual LightGBM tasks, pinned Chronos challenger, frozen feature/forecast/outcome store, archive/prospective training paths, experimental embeds, bounded production discovery bridge and research suspension logic. **No new model is approved for production or live trading. No production deployment or credential changes were made.** The baseline tag and old production model remain intact.

Audit scope and source references: [CRYPTO_ENGINE_AUDIT.md](CRYPTO_ENGINE_AUDIT.md). Setup, recovery and architecture: [CRYPTO_FORECASTING_SETUP.md](CRYPTO_FORECASTING_SETUP.md). Machine-readable evidence: [historical experiment](CRYPTO_ENGINE_EXPERIMENT_20261020.json), [bounded live probe](CRYPTO_ENGINE_LIVE_PROBE_20261020.json), [phase checklist](CRYPTO_ENGINE_PHASES.json).

## Historical experiment

Six official Binance spot archives: BTCUSDT/ETHUSDT, July–September 2025. All SHA-256 sidecars verified; microsecond timestamps explicitly normalized. Corpus: 92 calendar days per asset, sampled every 30 minutes to build **43,964 horizon-specific observations**. This is two established surviving assets, not a survivorship-free or full-market corpus. There is no historical L2, executable quote, liquidation or news reconstruction; unavailable features remain missing.

LightGBM trains six binary tasks per horizon (up, breakout, reversal, target-before-stop, volatility expansion and false breakout), plus continuous return and volatility regressors. Selection uses a small fixed 30/60-round family on validation only; calibration is a different chronological period and final holdout follows it. All assets share the same timestamp cuts. Label windows and actual later label receipt times are purged with embargo. Historical archived bar-availability is a replay assumption, not proof of the original data-vintage/revision history.

The mechanical second run added the requested continuous-volatility regressor and content-based model ID. All previously fitted task weights were verified unchanged. Both runs are preserved privately. It reused the same inspected holdout and therefore is **not new independent evidence**. Final pack: `lgbm-research-v2-2efed063fd7a098f`. The recorded training/Chronos evaluation run took approximately 25 seconds on the test CPU. Historical downloads and initial package/weight installation are excluded.

| Horizon | Holdout observations | Direction accuracy | LightGBM Brier | Training-prior Brier | Constant 0.5 Brier |
| --- | ---: | ---: | ---: | ---: | ---: |
| 5 minutes | 1,764 | 53.63% | 0.248995 | 0.249202 | 0.250000 |
| 15 minutes | 1,764 | 51.25% | 0.250184 | 0.250163 | 0.250000 |
| 1 hour | 1,764 | 48.64% | 0.251617 | 0.250695 | 0.250000 |
| 4 hours | 1,760 | 46.25% | 0.256360 | 0.254539 | 0.250000 |
| 24 hours | 1,744 | 43.69% | 0.261329 | 0.280586 | 0.250000 |

Each holdout contains 19 UTC days. The 5-minute paired day-block interval for improvement over the prior spans approximately **−0.00033 to +0.00073**. The 24-hour model improves on a poor shifted training prior but still loses to a constant 0.5 forecast. Long-horizon labels overlap heavily; counts are not independent trials. There are 30 binary task/horizon experiments and two regression families; no multiplicity-adjusted significance or performance superiority is claimed. Full precision/recall, false-positive/missed-opportunity rates, log loss, calibration bins, regimes and fold reports are in the JSON evidence.

Return prediction errors also matter: over the complete holdout, LightGBM return MAE did not beat the no-change reference at any of these five horizons. An apparent direction improvement does not establish a useful magnitude forecast or profitable entry. Nominal 80% residual intervals achieved measured coverage of approximately 73–84%, depending on horizon; their coverage is not guaranteed under new regimes.

## Matched Chronos comparison

Pinned `amazon/chronos-bolt-tiny`, revision `a0e552de83495b5c28c14c71c374f3e33280b340`, Apache-2.0. Ten predeclared evenly spaced holdout observations per horizon were evaluated on the **same timestamps and source instruments** as LightGBM and the simple references. Errors below are absolute percentage points of return, not trading returns:

| Horizon | LightGBM MAE | Chronos MAE | No-change MAE |
| --- | ---: | ---: | ---: |
| 5 minutes | 0.0812 | 0.0797 | 0.0825 |
| 15 minutes | 0.1294 | 0.1210 | 0.1305 |
| 1 hour | 0.1655 | 0.2400 | 0.1725 |
| 4 hours | 0.3048 | 0.3670 | 0.2932 |
| 24 hours | 1.3883 | 1.5492 | 1.0092 |

These are tiny descriptive samples, not a basis for selecting a winner. Typical measured model-call latency was roughly 5–13 ms on this CPU, excluding imports/downloads/network/warehouse. Raw Chronos interval coverage ranged from 60–90% on these tiny samples. Pretraining overlap is unknown. No calibrated Chronos probability or validated ensemble is claimed. Linear momentum is included in the JSON comparison and did not justify promotion either.

## After-cost research and old-engine reference

The new target-before-stop research policy used a fixed 0.60 probability cutoff and **40 bps all-in modeled round-trip cost**. It selected zero paper trades across the five horizons. Therefore after-cost expectancy and drawdown are unknown for that selected policy; zero trades are not a zero-loss profitable strategy. Do not lower the cutoff or retune the inspected holdout to manufacture performance.

The same archives were aggregated into 17,664 completed 15-minute candles for the unchanged old technical-strategy replay component. At the same explicit 40 bps assumption, BTC produced 333 simulated trades, approximately −0.339R mean return and 0.170 profit factor; ETH produced 364, approximately −0.270R mean return and 0.446 profit factor. This is **not** a replay of all production provider/identity/event/quote/model/portfolio gates, and is not the actual Discord bot's realized performance. It uses different trade definitions from the new horizon labels, so trade counts/returns are not a paired model superiority test. Historical multi-provider/microstructure and production-model artifacts are missing; a faithful complete-engine comparison remains blocked.

## Bounded live integration

A local authenticated Python service loaded the trained LightGBM artifact; a Node worker made two public-data passes separated by 15 seconds. No Discord channel or order route was used.

- Binance directory: **3,729 instruments; 1,380 active spot pairs**.
- In that observation window: **480 fresh observed pairs**; two selected detail candidates successfully passed Node→Python→warehouse, producing five frozen experimental horizons each.
- 53 source observations were rejected for stale/future/missing native time. They were not made fresh by receipt time.
- Coinbase fallback directory: **403 online USD products**. An initial fallback candle window was rejected as stale. The final primary-stream pass completed both forecast requests without failures.
- Final pass duration: approximately **1.85 seconds**, including public network/history and inference work. This is a small point-in-time probe, not sustained-load or comprehensive coverage verification.

The first probe exposed a real integration defect: legitimate Unicode Binance symbols caused the new validator to reject the entire directory. The repair retains exact Unicode venue identities and has a regression test. Coinbase's stale candle response was correctly rejected rather than presented as a healthy zero-opportunity scan.

The old realtime consensus path was also repaired: native timestamps remain separate from local receive time, and stale/future/unknown native times cannot count as fresh consensus. This may reduce confirmation when a feed lacks native time; that is a correctness change requiring forward observation, not a reason to invent freshness.

## Verification and remaining work

The preserved baseline passed 392 Node tests. The development changes add tests for quiet-market discovery, Unicode identities, timestamp failures, inactivity removal, exact identity bridging, unchanged detail budgets, bounded response memory, API cooldowns, experimental embeds and post-move labeling. Python tests exercise actual LightGBM fitting, separate calibration/holdout, delayed-label purging, immutable outcomes, five horizons, source revision failures, authenticated HTTP/body limits, read-only prospective retraining and matched research rollback. Final command counts are recorded in the phase checklist.

Still unverified or deliberately unavailable:

1. Sustained prospective predictive improvement, lead-time advantage and after-cost paper profitability. The short live probe cannot measure these.
2. Full-market historical representativeness, failed/delisted assets, native L2/news/liquidation vintages and historically achievable fills.
3. A matched replay of the entire existing multi-provider production engine and its actual deployed model artifacts.
4. A validated ensemble or automatic production promotion. Current prospective costs cannot pass the review gate; only research suspension/abstention is automatic.
5. Continuous all-market Coinbase/Kraken fallback, exhaustive DEX coverage and automatic DEX execution. Existing Kraken confirmation remains intact.
6. Production cPanel workload/entitlements and remote process/source hashes. No deployment was attempted.
7. Actual Discord delivery of the new research embeds, cross-host private transport configuration and sustained warehouse growth/recovery. Keep posting off until the intended research destination is tested.

The old model's blind-set conformal/residual reuse remains a documented baseline limitation; the new engine separates these datasets. Further fixes to the old learned uncertainty contract should be an independently reviewed/versioned change, not mixed silently into its historical comparison.
