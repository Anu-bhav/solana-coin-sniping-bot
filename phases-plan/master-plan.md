Okay, let's synthesize everything we've discussed from the repository analyses, video walkthroughs, API/library research, and safety considerations into a single, comprehensive, highly detailed Master Plan (v1.5). This plan prioritizes a modular, configurable, Devnet-first, safety-focused approach, aiming for self-reliance where possible while acknowledging potential necessary paid upgrades.

**Master Plan Report: Development of a Configurable Solana Pump.fun Sniper Bot (v1.5)**

**Version:** 1.5
**Date:** 2025-03-30

**1. Objective:**

To design, develop, test, and deploy a highly configurable Python-based automated trading bot. The bot will:
    *   **Detect:** Automatically identify Solana SPL tokens originating from Pump.fun the moment they migrate and add initial liquidity to a target DEX (Raydium or PumpSwap).
    *   **Filter:** Apply a rigorous, multi-stage, configurable filtering pipeline to mitigate risks associated with scams (honeypots, rugs, malicious contracts, manipulation patterns).
    *   **Execute:** Place buy orders with configurable parameters (amount, slippage, priority fees), supporting modular execution providers (Self-Built via RPC, potentially external APIs like Sniperoo).
    *   **Manage:** Monitor active positions and automatically execute sell orders based on configurable Take Profit (TP), Stop Loss (SL), and Time Stop criteria (primarily for self-built execution).
    *   **Persist State:** Utilize an SQLite database for robust state tracking (detections, filters, positions, history).
    *   **Be Configurable:** Manage all non-secret parameters, thresholds, feature toggles, and provider choices via a central `config.yml` file, validated rigorously at startup.
    *   **Prioritize Safety:** Employ a Devnet-first development strategy, extensive `dry_run` simulation, incremental testing, secure configuration handling, and controlled Mainnet deployment with minimal capital.
    *   **Aim for Self-Reliance:** Maximize the use of free libraries and free-tier APIs/RPC nodes initially, with a clear path for evaluating and integrating targeted paid upgrades only if essential bottlenecks are identified during testing.

**2. Disclaimer:**

This document outlines a plan for a high-risk, technically complex software project.
    *   **Financial Risk:** Sniping newly launched, low-liquidity tokens is exceptionally speculative. Over 90-95% of such tokens are scams or fail immediately. **Assume 100% loss of deployed capital is possible and likely, especially during testing.** This is NOT investment advice.
    *   **Technical Challenge:** Requires advanced Python (`asyncio`), Solana blockchain (`solana-py`, RPC), DEX protocol, API integration, and database skills.
    *   **No Guarantees:** A functional bot does not guarantee profitability. Success depends on speed, filter effectiveness, reliable execution, risk management, market conditions, and avoiding sophisticated scams.
    *   **Maintenance:** This requires ongoing monitoring, debugging, and adaptation to the rapidly evolving DeFi landscape.
    *   **Third-Party APIs:** Using external APIs (e.g., Sniperoo, RugCheck XYZ) introduces dependencies, potential costs, rate limits, and requires trusting their data/service reliability and security.

**3. Core Principles:**

*   **Devnet First:** All development and initial testing on Solana Devnet.
*   **Safety Focused:** Prioritize features preventing loss (filters, SL, `dry_run`, secure config).
*   **Configuration Driven:** All non-secret parameters controlled via `config.yml`, validated by `pydantic`. Secrets via `.env`.
*   **Modular Design:** Clear separation of concerns into distinct modules/services.
*   **Incremental Testing:** Test each component rigorously (unit, integration, E2E) upon implementation.
*   **Self-Reliance Prioritized:** Default to using free resources and self-built logic where feasible, evaluate paid upgrades based on data.

**4. Technology Stack:**

*   **Language:** Python 3.9+ (Recommend 3.10 or later)
*   **Core Solana:** `solana-py`
*   **Async HTTP Client:** `aiohttp`
*   **Async WebSockets:** `websockets` (or `aiohttp`'s client)
*   **Async Database:** `aiosqlite`
*   **Configuration:** `python-dotenv`, `PyYAML`
*   **Validation:** `pydantic`
*   **Logging:** `structlog`
*   **Testing:** `pytest`, `pytest-asyncio`

**5. Project Structure:**

```
pump_sniper_bot/
├── config/
│   └── config.yml        # Main configuration (non-secrets)
├── database/
│   ├── schema.sql        # SQLite schema definition
│   └── manager.py        # DB interaction logic (using aiosqlite)
├── logs/                 # Log files stored here
├── src/
│   ├── clients/          # Wrappers for external interactions
│   │   ├── __init__.py
│   │   ├── solana_client.py  # Wrapper around solana-py (RPC & WSS)
│   │   └── http_client.py    # Wrapper around aiohttp for REST APIs
│   ├── config/
│   │   ├── __init__.py
│   │   └── loader.py       # Loads .env, config.yml, validates with pydantic
│   ├── core/             # Core utilities and shared components
│   │   ├── __init__.py
│   │   ├── models.py       # Pydantic models for data structures (Config, Position, Trade etc.)
│   │   ├── state_tracker.py # In-memory state (maybe maps, sets), interacts with DatabaseManager
│   │   └── logger.py       # Structlog configuration
│   ├── execution_providers/ # Modular execution logic
│   │   ├── __init__.py
│   │   ├── base.py         # Abstract Base Class/Protocol for providers
│   │   ├── self_built.py   # Uses SolanaClient to build/send TXs
│   │   └── sniperoo.py     # Uses HttpClient to call Sniperoo API (optional)
│   ├── services/         # Core business logic orchestrators
│   │   ├── __init__.py
│   │   ├── detection_service.py
│   │   ├── filter_service.py
│   │   ├── execution_service.py
│   │   └── monitoring_service.py
│   ├── utils/            # Helper functions (e.g., formatting, time)
│   │   └── __init__.py
│   └── main.py           # Main application entry point, asyncio loop setup
├── tests/                # Unit and integration tests
│   ├── conftest.py       # Pytest fixtures
│   ├── unit/
│   └── integration/
├── .env.dev              # Secrets for Development (DO NOT COMMIT)
├── .env.prod             # Secrets for Production (DO NOT COMMIT)
├── .gitignore
├── pyproject.toml        # Or requirements.txt for dependencies
└── README.md
```

**Phase Breakdown & Detailed Actions:**

**Phase 0: Strategic Foundation & Prerequisite Setup (Week 0-1)**

*   **Action 0.1:** Solidify understanding of Solana, Pump.fun, target DEX Instructions (find **Devnet** Program IDs for Raydium/PumpSwap AMMs), and scam vectors.
*   **Action 0.2:** Install Python 3.9+, setup `venv`, initialize Git repository.
*   **Action 0.3:** Install core dependencies: `pip install solana aiohttp websockets aiosqlite python-dotenv pyyaml pydantic structlog pytest pytest-asyncio`. Generate `requirements.txt` or setup `pyproject.toml`.
*   **Action 0.4:** Create `config/config.yml` with the detailed, descriptive structure (see v1.4 example, refined further below). Include placeholders for all planned configurable items. Commit `config.yml` to Git.
*   **Action 0.5:** Create `.env.dev` and `.env.prod` templates. Add `.env*` to `.gitignore`. Populate `.env.dev` with:
    *   A **newly generated Devnet wallet** private key.
    *   Public Devnet RPC HTTP & WSS URLs (e.g., `api.devnet.solana.com`).
    *   Free Tier API Keys (Helius, DexScreener after signup).
*   **Action 0.6:** Implement `src/config/loader.py`. Define comprehensive `pydantic` models mirroring `config.yml`. Implement logic to load `.env` based on `APP_ENV`, load `config.yml`, validate rigorously with `pydantic`, and return the validated config object. Ensure failure on invalid config. Add unit tests for the loader and validation.
*   **Action 0.7:** Obtain sufficient Devnet SOL using a faucet for the Devnet wallet.
*   **Action 0.8:** Setup `src/core/logger.py` using `structlog` based on config settings (level, file output, format).

**Phase 1: Core Clients & Database (Weeks 2-4)**

*   **Action 1.1:** Implement `src/database/schema.sql` defining tables (`detections`, `positions`, `trades` with appropriate fields and indexes).
*   **Action 1.2:** Implement `src/database/manager.py` (`DatabaseManager` class).
    *   Use `aiosqlite` for async operations.
    *   Load DB path from config based on `APP_ENV`.
    *   Implement `initialize_db()` (connect, create tables if not exist using schema).
    *   Implement CRUD functions with `async`: `add_detection`, `update_detection_status`, `add_position`, `update_position_status`, `get_position_by_token`, `move_position_to_trades`, `check_if_token_processed`, `check_if_creator_processed`.
    *   **Implement `UPSERT` logic** for adding/updating records where appropriate (e.g., updating position status).
    *   Unit test DB functions extensively, mocking `aiosqlite`.
*   **Action 1.3:** Implement `src/clients/solana_client.py` (`SolanaClient` class).
    *   Load RPC URLs/timeout from validated config.
    *   Implement `async` wrappers for `solana-py`: connect, load keypair, basic gets (`getBalance`, `getAccountInfo`), TX building (`build_swap_instruction` for Raydium/PumpSwap Devnet IDs), TX sending (`create_sign_send_transaction` with priority fee logic from config), confirmation, WSS connection/subscription (`start_log_subscription` targeting Program IDs from config).
    *   Implement `dry_run` parameter in `create_sign_send_transaction`.
    *   Implement basic retry and rate limit awareness (delay on 429).
    *   Unit test using `pytest-asyncio` and mocking `AsyncClient`.
*   **Action 1.4:** Implement `src/clients/http_client.py` (`HttpClient` class).
    *   Wrapper around `aiohttp.ClientSession`.
    *   Implement `async get`, `async post` methods.
    *   Load API keys from loaded secrets (via config loader).
    *   Handle request building, headers (e.g., Bearer tokens), JSON parsing, timeouts (from config), retries (from config), rate limit errors (HTTP 429 -> delay from config), other HTTP errors.
    *   Unit test using `aiohttp.pytest_plugin` or mocks.

**Phase 2: Detection & Filtering Services (Weeks 5-9)**

*   **Action 2.1:** Implement `src/services/detection_service.py`.
    *   Use `SolanaClient` to connect via WSS (Devnet).
    *   Use `start_log_subscription` with Program IDs from config.
    *   Implement message handler (`on_message`) to parse logs, extract TX signature, call `SolanaClient.getParsedTransaction` (or equivalent) to get token mints/LP address.
    *   Perform initial source filtering (SOL pair? Pump.fun origin?).
    *   Queue valid candidates (`(token_mint, base_mint, lp_address)`) using `asyncio.Queue`.
    *   Implement WSS reconnection logic using config delay.
    *   Test log parsing logic with sample Devnet data. Integration test WSS connection/parsing later.
*   **Action 2.2:** Implement `src/services/filter_service.py`.
    *   Consume items from the detection queue.
    *   For each candidate, execute the filtering pipeline based on `config.filtering`:
        *   `_run_contract_liquidity_checks`: If `config.filtering.contract_liquidity_checks.enabled`:
            *   Call `SolanaClient` for Mint/Freeze authority if `config...check_mint_freeze_authority.enabled`. Fail if `config...fail_if_authority_exists` is true and authority found.
            *   Call `SolanaClient` for liquidity if `config...check_initial_liquidity.enabled`. Fail if below `config...min_liquidity_usd`.
            *   Call `SolanaClient` for LP status if `config...check_lp_status.enabled`. Fail/Warn based on `config...require_lp_burned`.
        *   `_run_metadata_distribution_checks`: If `config.filtering.metadata_distribution_checks.enabled`:
            *   Call `HttpClient` (using provider from `config...check_socials_presence.api_provider`) for socials if `config...check_socials_presence.enabled`. Fail if `config...fail_if_missing` and none found. Handle rate limits.
            *   Skip holder distribution, deployer holdings, SOL balance checks initially (respect `enabled: false` in config). Implement later if needed/feasible.
        *   `_run_trading_pattern_checks`: Skip initially (respect `enabled: false` in config).
        *   `_run_duplicate_history_checks`: If `config.filtering.duplicate_history_checks.enabled`: Call `DatabaseManager` to check DB based on `block_returning_token_names`/`_creators` flags. Requires identifying creator (potentially slow).
        *   `_run_external_rug_checks`: Skip initially (respect `enabled: false`). Implement later if API found and configured.
    *   Log detailed pass/fail for each enabled check.
    *   Update token status in DB via `DatabaseManager.update_detection_status`.
    *   If all enabled critical checks pass, queue validated data for Execution Service.
    *   **Unit test** each filter group logic extensively, mocking dependencies and testing against various config settings.

**Phase 3: Execution Providers & Monitoring Service (Weeks 10-13)**

*   **Action 3.1:** Define `src/execution_providers/base.py` interface (`ExecutionProvider` ABC).
*   **Action 3.2:** Implement `src/execution_providers/self_built.py` (`SelfBuiltProvider`).
    *   Takes `SolanaClient`, `DatabaseManager`, relevant config.
    *   Implements `execute_buy`: Builds swap TX using `SolanaClient`, applies fees/Jito from config, sends TX (respecting `dry_run`), confirms, calls `DatabaseManager.add_position` on real success.
    *   Implements `execute_sell`: Builds sell swap TX, sends, confirms, calls `DatabaseManager.move_position_to_trades`.
    *   Unit test heavily with mocks.
*   **Action 3.3:** (Optional) Implement `src/execution_providers/sniperoo.py` (`SniperooProvider`).
    *   Takes `HttpClient`, `DatabaseManager`, relevant config/secrets.
    *   Implements `execute_buy`: Formats Sniperoo API request body (inc. auto-sell params from config), calls API via `HttpClient`, handles response, updates DB. Respects `dry_run`.
    *   Implement `execute_sell` only if `config.sniperoo_api_settings.auto_sell_enabled` is false.
    *   Unit test with mocked `HttpClient`.
*   **Action 3.4:** Implement `src/services/execution_service.py`.
    *   Consumes from filter queue.
    *   Loads config, dynamically instantiates the selected execution provider (`SELF_BUILT` or `SNIPEROO_API`).
    *   Calls `provider.execute_buy`, passing relevant shared parameters (`buy_amount_sol`) and `dry_run` flag.
    *   Logs provider response/signature/identifier.
    *   Unit test dynamic loading and delegation.
*   **Action 3.5:** Implement `src/services/monitoring_service.py`.
    *   Main loop checks `config.monitoring.enabled` AND depends on `config.execution.provider` setting. Runs only if needed (Self-Built or Sniperoo without auto-sell).
    *   Periodically (`config...price_poll_interval_seconds`):
        *   Fetch active positions from `DatabaseManager`.
        *   For each position, fetch current price using chosen `config...price_provider` (RPC or API via `HttpClient`, handle rate limits).
        *   Check TP/SL/Time Stop conditions using thresholds from config.
        *   If triggered, call `ExecutionManager` (which delegates to the loaded provider's `execute_sell`).
    *   Unit test monitoring loop, price fetching mocks, trigger logic, interaction with Execution Manager/DB.

**Phase 4: Integration, Logging, Testing, Safety Protocols (Weeks 14-16)**

*   **Action 4.1:** Implement `main.py`.
    *   Load validated config via `loader`.
    *   Initialize DB (`DatabaseManager.initialize_db`).
    *   Initialize clients (`SolanaClient`, `HttpClient`).
    *   Initialize services (`Detection`, `Filter`, `Execution`, `Monitoring`), passing config and dependencies. Instantiate correct Execution Provider in Manager.
    *   Setup `asyncio` queues and tasks for each service.
    *   Implement main loop and graceful shutdown handling.
*   **Action 4.2:** **Integration Testing:**
    *   Test queue interactions (Detection->Filter->Execution).
    *   Test StateTracker/DatabaseManager interactions from Filter/Execution/Monitor services.
    *   Run with `dry_run=True`, using mocked detection events.
*   **Action 4.3:** **End-to-End Devnet Testing (`dry_run=True`):**
    *   Run full system connected to Devnet WSS/RPC/APIs.
    *   Wait for real Devnet pool creations or manually trigger test scenarios.
    *   Verify log output for detection, filtering (pass/fail reasons based on config), state updates (check SQLite DB manually), and *simulated* buy/sell logs from Execution Manager.
*   **Action 4.4:** **End-to-End Devnet Testing (`dry_run=False`):**
    *   Use Devnet SOL (minimal amounts configured).
    *   Manually create test pools/tokens on Devnet representing:
        *   A "good" token (valid authorities, LP burned, socials present).
        *   A token with mint/freeze authority enabled.
        *   A token with unlocked LP.
        *   A token with no social metadata.
        *   A token from a previously seen creator (for duplicate check).
    *   Run the bot and verify:
        *   Correct detection.
        *   Correct filtering decisions based on config.
        *   Successful execution of BUY via the selected provider (check Solscan Devnet).
        *   Correct entry in `positions` table in SQLite DB.
        *   Correct position monitoring (infrequent price checks).
        *   Correct execution of TP/SL via the selected provider (check Solscan Devnet).
        *   Correct update to `trades` table in SQLite DB.
    *   Test BOTH `SELF_BUILT` and `SNIPEROO_API` (if implemented) execution providers thoroughly on Devnet.
    *   Test robustness: Simulate RPC/API errors, WSS disconnects. Verify reconnection and error handling.
*   **Action 4.5:** Implement basic health check logging/endpoint.
*   **Action 4.6:** Conduct code reviews focusing on security, error handling, async best practices, and configuration usage.

**Phase 5: Controlled Mainnet Transition & Iteration (Ongoing - Proceed Cautiously)**

*   **Action 5.1:** Complete Rigorous Pre-Flight Checklist (All Devnet tests pass? Mainnet Config Ready? **NEW Mainnet Wallet** funded minimally? Monitoring active?). **Backup Prod DB and Config.**
*   **Action 5.2:** Deploy to secure Mainnet VPS. Run with `APP_ENV=production`, **`dry_run=True`**. Monitor against live Mainnet events for >= 24 hours. Check logs, resource usage, errors, rate limits.
*   **Action 5.3:** **First Live Mainnet Trades:** Set `buy_amount_sol` to absolute minimum ($5-$10). Set `dry_run=False`. **Monitor 24/7.** Watch logs, Solscan, wallet balance. Be ready to stop manually via SSH/kill switch. Verify first live buy/sell cycle and DB updates.
*   **Action 5.4:** **Performance Evaluation:** After a sufficient period (days/weeks) of micro-capital trading, analyze:
    *   Filter Hit Rate: How many detected tokens pass filters? How many were scams?
    *   Execution Success Rate: How often do buy/sell TXs succeed/fail/timeout?
    *   Profitability (Net of Fees/Slippage): Is it losing money (most likely)?
    *   Bottlenecks: Where are the delays/failures? RPC? APIs? Execution?
*   **Action 5.5:** **Decision & Iteration:** Based on evaluation:
    *   **Tune:** Adjust `config.yml` thresholds, fees, timings.
    *   **Upgrade:** If RPC is the bottleneck, upgrade to paid RPC. Re-test. If data APIs limit filtering, consider paid tiers or implementing more robust self-reliant checks if possible. If execution fails, consider trying the Sniperoo provider (if implemented/researched) or further optimizing self-built logic/fees.
    *   **Halt:** If fundamentally unworkable or too loss-making.
    *   **Scale:** Only if *proven*, consistent (even if small) positive performance is achieved over time, increase size *very gradually*.
*   **Action 5.6:** Ongoing maintenance (monitoring, debugging, adapting).

This v1.5 Master Plan provides an extremely detailed, phased approach incorporating all requirements and safety measures. Remember, flexibility and objective evaluation based on testing data (especially during the initial Mainnet phase) will be crucial for navigating the challenges of this project.