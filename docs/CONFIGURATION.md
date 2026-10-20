# Configuration reference

Generated from `crypto-bot/.env.example`. Copy the template, never another person's `.env`. Template defaults are starting settings, not account/risk recommendations. Read its comments and source before changing a safety control.

| Variable | Template default | Role |
| --- | --- | --- |
| `DISCORD_TOKEN` | your own value; optional when its source is disabled | Private credential from your own account/application. |
| `DISCORD_CLIENT_ID` | your own value; optional when its source is disabled | Your own server/application/account identifier. |
| `DISCORD_GUILD_ID` | your own value; optional when its source is disabled | Your own server/application/account identifier. |
| `PORT` | 3000 | Runtime, data-source, cost, review or safety setting; see template comments. |
| `TIMEZONE` | America/Chicago | Runtime, data-source, cost, review or safety setting; see template comments. |
| `CRYPTO_MONITOR_MINUTES` | 5 | Runtime, data-source, cost, review or safety setting; see template comments. |
| `CRYPTO_DISCOVERY_MINUTES` | 15 | Runtime, data-source, cost, review or safety setting; see template comments. |
| `CRYPTO_DAILY_HOUR` | 7 | Runtime, data-source, cost, review or safety setting; see template comments. |
| `CRYPTO_DAILY_MINUTE` | 0 | Runtime, data-source, cost, review or safety setting; see template comments. |
| `CRYPTO_MIN_SCORE` | 64 | Runtime, data-source, cost, review or safety setting; see template comments. |
| `CRYPTO_MAX_SIGNALS` | 5 | Runtime, data-source, cost, review or safety setting; see template comments. |
| `CRYPTO_MAX_MARKET_RANK` | 250 | Runtime, data-source, cost, review or safety setting; see template comments. |
| `CRYPTO_BROAD_DISCOVERY_ENABLED` | true | Runtime, data-source, cost, review or safety setting; see template comments. |
| `CRYPTO_VENUE_DISCOVERY_ENABLED` | true | Runtime, data-source, cost, review or safety setting; see template comments. |
| `CRYPTO_VENUE_RESEARCH_CANDIDATES` | 2 | Runtime, data-source, cost, review or safety setting; see template comments. |
| `CRYPTO_MIN_VOLUME_USD` | 5000000 | Runtime, data-source, cost, review or safety setting; see template comments. |
| `CRYPTO_MIN_PROVIDER_CONFIRMATIONS` | 2 | Runtime, data-source, cost, review or safety setting; see template comments. |
| `CRYPTO_MAX_DISCOVERY_ASSET_AGE_MINUTES` | 30 | Runtime, data-source, cost, review or safety setting; see template comments. |
| `CRYPTO_MAX_PROVIDER_CANDIDATES` | 8 | Runtime, data-source, cost, review or safety setting; see template comments. |
| `CRYPTO_MIN_RISK_REWARD` | 1.7 | Runtime, data-source, cost, review or safety setting; see template comments. |
| `CRYPTO_ACCOUNT_RISK_PCT` | 0.5 | Runtime, data-source, cost, review or safety setting; see template comments. |
| `CRYPTO_ROUND_TRIP_FEE_BPS` | 20 | Runtime, data-source, cost, review or safety setting; see template comments. |
| `CRYPTO_MAX_CONCURRENT_SIGNALS` | 3 | Runtime, data-source, cost, review or safety setting; see template comments. |
| `CRYPTO_MAX_OPEN_RISK_PCT` | 1.5 | Runtime, data-source, cost, review or safety setting; see template comments. |
| `CRYPTO_GUARD_MAX_DAILY_LOSS_R` | 3 | Runtime, data-source, cost, review or safety setting; see template comments. |
| `CRYPTO_MAX_SIGNAL_CORRELATION` | 0.82 | Runtime, data-source, cost, review or safety setting; see template comments. |
| `CRYPTO_META_MIN_SAMPLES` | 200 | Runtime, data-source, cost, review or safety setting; see template comments. |
| `CRYPTO_META_RETRAIN_HOURS` | 24 | Runtime, data-source, cost, review or safety setting; see template comments. |
| `CRYPTO_MIN_META_PROBABILITY` | 0.56 | Runtime, data-source, cost, review or safety setting; see template comments. |
| `CRYPTO_RESEARCH_RETENTION_DAYS` | 730 | Runtime, data-source, cost, review or safety setting; see template comments. |
| `CRYPTO_GUARD_ROLLING_WINDOW` | 30 | Runtime, data-source, cost, review or safety setting; see template comments. |
| `CRYPTO_GUARD_MIN_OUTCOMES` | 20 | Runtime, data-source, cost, review or safety setting; see template comments. |
| `CRYPTO_GUARD_MAX_DRAWDOWN_R` | 5 | Runtime, data-source, cost, review or safety setting; see template comments. |
| `CRYPTO_GUARD_MIN_EXPECTANCY_R` | 0 | Runtime, data-source, cost, review or safety setting; see template comments. |
| `CRYPTO_GUARD_MAX_BRIER` | 0.28 | Runtime, data-source, cost, review or safety setting; see template comments. |
| `CRYPTO_GUARD_LOOKBACK_HOURS` | 168 | Runtime, data-source, cost, review or safety setting; see template comments. |
| `CRYPTO_DERIVATIVES_ENABLED` | true | Runtime, data-source, cost, review or safety setting; see template comments. |
| `CRYPTO_REALTIME_ENABLED` | true | Runtime, data-source, cost, review or safety setting; see template comments. |
| `CRYPTO_MICROSTRUCTURE_ENABLED` | true | Runtime, data-source, cost, review or safety setting; see template comments. |
| `CRYPTO_MICROSTRUCTURE_FLUSH_SECONDS` | 300 | Runtime, data-source, cost, review or safety setting; see template comments. |
| `CRYPTO_SIMULATED_ORDER_USD` | 1000 | Runtime, data-source, cost, review or safety setting; see template comments. |
| `CRYPTO_EXECUTION_LATENCY_MS` | 750 | Runtime, data-source, cost, review or safety setting; see template comments. |
| `CRYPTO_MAX_EXECUTION_SLIPPAGE_BPS` | 35 | Runtime, data-source, cost, review or safety setting; see template comments. |
| `CRYPTO_VALIDATION_FOLDS` | 4 | Runtime, data-source, cost, review or safety setting; see template comments. |
| `CRYPTO_BLIND_HOLDOUT_FRACTION` | 0.15 | Runtime, data-source, cost, review or safety setting; see template comments. |
| `CRYPTO_CONFORMAL_ALPHA` | 0.20 | Runtime, data-source, cost, review or safety setting; see template comments. |
| `CRYPTO_MAX_OOD_SCORE` | 4 | Runtime, data-source, cost, review or safety setting; see template comments. |
| `CRYPTO_CHALLENGER_MIN_SAMPLES` | 50 | Runtime, data-source, cost, review or safety setting; see template comments. |
| `CRYPTO_CHALLENGER_BRIER_IMPROVEMENT` | 0.005 | Runtime, data-source, cost, review or safety setting; see template comments. |
| `CRYPTO_EVENT_VETO_ENABLED` | true | Runtime, data-source, cost, review or safety setting; see template comments. |
| `CRYPTO_CATALYST_SOURCE` | manual | Runtime, data-source, cost, review or safety setting; see template comments. |
| `FINNHUB_API_KEY` | your own value; optional when its source is disabled | Private credential from your own account/application. |
| `CRYPTO_HISTORICAL_IMPORT_DIR` | (empty; review before enabling) | Runtime, data-source, cost, review or safety setting; see template comments. |
| `COINGECKO_API_KEY` | your own value; optional when its source is disabled | Private credential from your own account/application. |
| `COINGECKO_API_TIER` | demo | Runtime, data-source, cost, review or safety setting; see template comments. |
| `DEFILLAMA_API_KEY` | your own value; optional when its source is disabled | Private credential from your own account/application. |
| `DEFILLAMA_HACKS_ENABLED` | false | Runtime, data-source, cost, review or safety setting; see template comments. |
| `GITHUB_TOKEN` | your own value; optional when its source is disabled | Private credential from your own account/application. |
| `OMNIMOD_CRYPTO_DATA_DIR` | (empty; review before enabling) | Runtime, data-source, cost, review or safety setting; see template comments. |
| `POST_ON_START` | true | Runtime, data-source, cost, review or safety setting; see template comments. |
| `CRYPTO_AUTO_PROVISION` | false | Runtime, data-source, cost, review or safety setting; see template comments. |
| `OMNIMOD_PAPER_ACCOUNT_EQUITY_USD` | 0 | Runtime, data-source, cost, review or safety setting; see template comments. |
| `TRADING_RISK_STATE_PATH` | (empty; review before enabling) | Runtime, data-source, cost, review or safety setting; see template comments. |
| `OMNIMOD_EMERGENCY_STOP` | true | Runtime, data-source, cost, review or safety setting; see template comments. |
| `SHARED_MAX_QUOTE_AGE_MS` | 15000 | Runtime, data-source, cost, review or safety setting; see template comments. |
| `SHARED_MAX_OPEN_MARK_AGE_MS` | 300000 | Runtime, data-source, cost, review or safety setting; see template comments. |
| `SHARED_MAX_OPEN_POSITIONS` | 5 | Runtime, data-source, cost, review or safety setting; see template comments. |
| `SHARED_MAX_TRADE_RISK_PCT` | 0.25 | Runtime, data-source, cost, review or safety setting; see template comments. |
| `SHARED_MAX_TOTAL_OPEN_RISK_PCT` | 1 | Runtime, data-source, cost, review or safety setting; see template comments. |
| `SHARED_MAX_GROSS_EXPOSURE_PCT` | 150 | Runtime, data-source, cost, review or safety setting; see template comments. |
| `SHARED_MAX_DAILY_LOSS_PCT` | 1 | Runtime, data-source, cost, review or safety setting; see template comments. |
| `SHARED_MAX_SPREAD_PCT` | 0.5 | Runtime, data-source, cost, review or safety setting; see template comments. |
| `SHARED_MIN_REWARD_RISK` | 1.25 | Runtime, data-source, cost, review or safety setting; see template comments. |
| `PAPER_MONITOR_INTERVAL_SECONDS` | 0 | Runtime, data-source, cost, review or safety setting; see template comments. |

## Optional forecasting research

| Variable | Default | Role |
| --- | --- | --- |
| `CRYPTO_FORECAST_DISCOVERY_BRIDGE_ENABLED` | false | Opt-in exact-identity discovery bridge; one existing detail slot, unchanged final gates. |

Additional separate-worker settings and secret handling are documented in [CRYPTO_FORECASTING_SETUP.md](CRYPTO_FORECASTING_SETUP.md) and [the forecasting template](../crypto-bot/.env.forecasting.example).
