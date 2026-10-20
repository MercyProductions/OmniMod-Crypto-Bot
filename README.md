# OmniMod Crypto Bot

Discover supported crypto assets and venue products, validate day-trading hypotheses, and track qualified paper setups. `npm start` launches **only Crypto**. Automated tests establish code behavior; current provider coverage and forward performance require separate evidence.

## Forecasting engine development upgrade

The opt-in LightGBM/Chronos research engine is on `feat/crypto-forecasting-engine-2026-10-20`; it has not been deployed or approved for live trading. Start with the [audit](docs/CRYPTO_ENGINE_AUDIT.md), [setup and developer handoff](docs/CRYPTO_FORECASTING_SETUP.md), [measured results](docs/CRYPTO_ENGINE_RESULTS.md) and [phase checklist](docs/CRYPTO_ENGINE_PHASES.json). The pre-upgrade source is preserved as `baseline/pre-crypto-forecasting-2026-10-20`.

The engine includes streaming venue discovery, a bounded detail funnel, five forecast horizons, real Python model training/inference and frozen prospective observations/outcomes. The historical experiment did not establish profitable trading or justify promotion. Experimental forecasts remain separate from the existing production approval/risk chain. Free public data and optional paid-provider paths have different coverage; no claim of scanning every cryptocurrency is made.

## How it works

1. Combine broad asset-directory and venue discovery with a cheap liquidity/movement screen. Displayed highlights are a subset of the universe.
2. Resolve exact asset/product identity, quote currency and native size/price rules; ambiguous tickers cannot become executable identities.
3. Deep-analyze selected candidates using completed candles, trend/momentum, liquidity and multi-provider quote evidence, plus available derivatives context.
4. Apply chronological strategy checks, confirmation, catalyst review and portfolio gates. Venue shadow observations and longer-horizon research are separate tracks.
5. Use later fresh quotes and observed liquidity for paper fills/exits. A heuristic rank is not a calibrated profit probability.

Highlights are not the full universe and watches are not automatically approved entries. Model probability, heuristic strength and data quality have different meanings. Zero results can mean a closed session, disabled provider, missing evidence, pending model or risk rejection.

## Requirements and layout

Use Git, **Node.js 22.9+** (the export was checked with Node 24), npm and your own Discord app/server. The primary project is [`crypto-bot/`](crypto-bot/). The existing six-market source integration bundle is preserved because shared adapters/tests import sibling projects. Their presence does not start those bots. The root wrapper selects only this repository’s named application.

`repository.json` records the original export/source hashes. Later Git commits/tags are authoritative for subsequent changes. Dependencies remain locked in the existing project lockfiles.

## Install from a clean checkout

```sh
git clone https://github.com/MercyProductions/OmniMod-Crypto-Bot.git
cd OmniMod-Crypto-Bot
npm run bootstrap
npm run info
npm test
npm run check
```

Bootstrap installs locked dependencies with lifecycle scripts disabled. It does not create a provider subscription. Tests use isolated fixture/mocked inputs.

Copy the template on Windows PowerShell:

```powershell
Copy-Item crypto-bot/.env.example crypto-bot/.env
```

Or on Linux/macOS:

```sh
cp crypto-bot/.env.example crypto-bot/.env
```

Edit that **local** `.env`; never copy the maintainer’s tokens or publish your file. [Every shipped template setting is listed here](docs/CONFIGURATION.md), with sensitive values replaced by instructions to supply your own.

## Create your own Discord application

1. In the [Developer Portal](https://discord.com/developers/applications), create your own application and bot user. Choose its name/avatar.
2. Reset/copy its bot token into `DISCORD_TOKEN`; set the application ID as `DISCORD_CLIENT_ID`. They are different values. Each independently running bot needs its own application/token.
3. Enable Discord Developer Mode and copy your server ID to `DISCORD_GUILD_ID`. Configure your setup-command channel selections; never reuse the owner’s destination IDs.
4. Install it to your server with `bot` and `applications.commands` scopes. Allow View Channel, Send Messages, Embed Links and Read Message History in its channels. Setup that creates channels/roles needs the corresponding management permission.
5. Register commands and start this application:

```sh
npm run register
npm start
```

Use `/crypto setup` in your server to select destinations/roles. Registration/startup connects to your own Discord application and can publish messages. A connected gateway does not establish feed readiness.

The identity skeleton is deliberately empty:

```dotenv
DISCORD_TOKEN=
DISCORD_CLIENT_ID=
DISCORD_GUILD_ID=
```

Add the project’s own destination/provider fields from its template. Do not share tokens in issues, screenshots or pull requests.

## Free data and paid upgrades

| Source | Role | Settings in local .env | Limits / prerequisites |
| --- | --- | --- | --- |
| Public discovery/exchanges | Keyless fallback | COINGECKO_API_TIER=public; COINGECKO_API_KEY empty | Public CoinGecko/CoinPaprika and Binance/Coinbase/Kraken adapters can be throttled, restricted or incomplete. |
| CoinGecko Demo | Optional account key | COINGECKO_API_TIER=demo; COINGECKO_API_KEY | Use a Demo key for Demo mode. |
| CoinGecko Pro | Optional paid upgrade | COINGECKO_API_TIER=pro; COINGECKO_API_KEY | Use a Pro key; venue confirmation and risk gates remain required. |
| Finnhub / DeFiLlama / GitHub | Optional enrichment | FINNHUB_API_KEY / DEFILLAMA_API_KEY / GITHUB_TOKEN | Only implemented adapters are used; some enrich longer-horizon research. |

Review this mode skeleton; blank credentials intentionally do not authenticate:

```dotenv
COINGECKO_API_TIER=public
COINGECKO_API_KEY=
CRYPTO_BROAD_DISCOVERY_ENABLED=true
CRYPTO_VENUE_DISCOVERY_ENABLED=true
OMNIMOD_EMERGENCY_STOP=true
OMNIMOD_LIVE_TRADING_ENABLED=false
```

The [configuration reference](docs/CONFIGURATION.md) lists all shipped variables. A key enables only the implemented adapters, not every endpoint sold by the provider. Read the primary project’s [existing technical guide](crypto-bot/README.md) for deeper settings and market-specific workflows.

### Preview provider profiles

```sh
npm --prefix new-bots run data:setup -- --bot crypto --profile free
npm --prefix new-bots run data:setup -- --list
```

Without `--apply`, this previews settings/missing prerequisites without editing `.env` or calling a provider. A free profile can be unsupported (Futures) or observation-only (limited/delayed feeds). Upgrade names differ by bot: inspect `--list` rather than assuming every market has a `paid` profile. Use `--apply` only after adding your own credentials and reviewing selectors. Equity, cost reserves, contract reviews and catalysts still require configuration.

## Paper accounts and shared risk

No live order route is implemented. Keep `OMNIMOD_LIVE_TRADING_ENABLED=false`. The emergency stop defaults to true. For paper reservations, deliberately configure positive paper equity, instrument-specific fees/slippage, current catalyst evidence and reviewed risk limits before setting `OMNIMOD_EMERGENCY_STOP=false`.

Stocks/Crypto use `OMNIMOD_PAPER_ACCOUNT_EQUITY_USD`; the other four bots use `PAPER_ACCOUNT_EQUITY_USD`. The first reservation anchors that ledger’s equity. A missing validated model, quote, review, cost assumption or account basis can block entries while discovery still operates.

For multiple clones on one computer, set the **same absolute `TRADING_RISK_STATE_PATH` and `OMNIMOD_SIGNAL_RESEARCH_PATH`** in every participating bot’s private configuration. Separate clones have separate default portfolios. Match equity/cost assumptions and keep marks current. File locks do not coordinate different hosts. Shared research never overrides the primary owner’s strategy/risk approval.

Watch, reservation, fill and target-hit counts have different meanings. Paper entry requires a later eligible quote. Stops/targets/excursions/returns are quote-sampled simulations after recorded costs, not calibrated broker fills. See [shared risk](new-bots/shared/paperRisk.js) and [fill checks](new-bots/shared/FILL_PORTFOLIO_RISK.md).

## Configure an account step by step

For keyless operation leave `COINGECKO_API_KEY` empty and use the public tier; no exchange trading key is needed for the public exchange adapters. For Demo, obtain your own key from the CoinGecko developer dashboard and set tier `demo`. For a Pro subscription use its own key and tier `pro`. A tier/key mismatch can fail authentication. Run the public-funnel probe to inspect discovery and venue confirmation separately; paid discovery does not bypass confirmation or strategy validation.

## Operation and diagnostics

/crypto setup, /crypto status, /crypto diagnostics, /crypto scan, /crypto tracker, /crypto performance and /crypto validate. /crypto invest is separate research.

Additional commands from this repository root:

```sh
npm --prefix crypto-bot run probe:public-funnel
npm --prefix crypto-bot run monitor:paper
```

Probes/scans can contact the configured provider; metered history or explicit odds refresh may consume your credits. Review request/cost caps first. Do not start duplicate workers against one Discord identity/data store.

| Symptom | Check |
| --- | --- |
| No slash commands | Own token/client-ID pair, correct guild installation, registration and permissions. |
| Connected but zero candidates | Selected source, discovery/screen counts, session, current inputs and rejected-gate reasons. |
| HTTP 401/403 | Key validity, account region/permissions and endpoint entitlement; do not report it as no opportunities. |
| HTTP 429 | Quota headers, cooldown/concurrency and duplicate workers sharing the same provider account. |
| Watches without setups | Data age, model readiness, confirmation, catalyst evidence, explicit costs, emergency stop and risk limits. |
| Unexpected result summary | Separate research/shadow observations, issued alerts, delivery and actual paper fills. Consult durable records. |
| Stale records after restart | Actual data path/OS user, timezone, last successful request and old state; preserve the store when investigating. |

Runtime stores can contain private server settings and credentials saved by admin commands. Keep them outside Git/public web roots, persist them across restarts and back them up privately before upgrades. Original hosting documents may describe older deployments; source publication does not configure cPanel or start a production service.

## Baseline and contributing

The pre-change version is preserved as [`baseline/pre-readme-sports-audit-2026-10-20`](https://github.com/MercyProductions/OmniMod-Crypto-Bot/tree/baseline/pre-readme-sports-audit-2026-10-20), commit `8be3e071766f080c69486af5dd0c063cb6183ef8`. Inspect it without erasing later work:

```sh
git switch -c inspect-baseline baseline/pre-readme-sports-audit-2026-10-20
```

Fork, create a development branch and use your own local credentials. Add regression tests for confirmed defects. Freeze model/strategy versions, dates, horizons and costs before evaluating changes. Compare the same chronological out-of-sample game/trade populations, reporting proper scores/calibration, sample sizes, costs and unresolved outcomes. A few good days or more alerts do not establish improvement. Preserve source and private runtime evidence before model changes.

`npm test` runs this primary project’s tests. `npm run check` runs configured syntax checks. `npm run test:all` checks the full shared/new-market, Stocks and Crypto integration bundle. Submit the problem/change/checks/limits in your PR; share sanitized diagnostics rather than private state.

## Source map

- [Discovery](crypto-bot/src/cryptoData.js)
- [Decision pipeline](crypto-bot/src/predictionEngine.js)
- [Venue confirmation](crypto-bot/src/marketProviders.js)

## Provider documentation

- [Discord setup](https://docs.discord.com/developers/quick-start/getting-started)
- [Alpaca coverage](https://docs.alpaca.markets/us/docs/about-market-data-api)
- [CoinGecko Demo authentication](https://docs.coingecko.com/demo/reference/authentication)
- [OANDA API access](https://developer.oanda.com/rest-live-v20/introduction/)
- [Databento access](https://databento.com/docs/getting-started/build-first-app)
- [Tradier sandbox/data differences](https://docs.tradier.com/docs/market-data)
- [The Odds API v4](https://the-odds-api.com/liveapi/guides/v4/)

References checked on 2026-10-20. Confirm current region, licensing, quota and endpoint entitlement in your own account before enabling a paid selector. Each contributor needs their own provider account; this code does not redistribute the maintainer’s data subscriptions.
