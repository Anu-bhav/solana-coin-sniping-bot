# Phase 3: Execution & Position Management Implementation

**Goal:** Implement the logic for executing buy/sell orders based on filtered candidates and managing active positions according to configured Take Profit (TP), Stop Loss (SL), and Time Stop rules. This phase introduces the modular execution provider system.

**Duration Estimate:** 3-4 Weeks

**Key Activities & Actions:**

1.  **Execution Provider Interface Definition (`src/execution_providers/base.py`):**
    *   Define an Abstract Base Class (ABC) or Protocol named `ExecutionProvider`.
    *   Define core `async` methods that all providers must implement:
        *   `initialize(self, config: dict, secrets: dict, clients: dict)`: Allows passing necessary config sections, loaded secrets (like API keys), and shared clients (`SolanaClient`, `HttpClient`).
        *   `execute_buy(self, token_mint: str, base_mint: str, lp_address: str, amount_sol: float, dry_run: bool = False) -> Tuple[Optional[str], Optional[str]]`: Attempts to execute the buy. Takes necessary token/pool info. Returns a tuple `(status, identifier)`, where `status` could be 'SUCCESS', 'FAILED', 'SIMULATED_SUCCESS', 'SIMULATED_FAILED', 'PENDING' and `identifier` could be a transaction signature, Sniperoo trade ID, or None.
        *   `execute_sell(self, position_id: int, token_mint: str, base_mint: str, amount_tokens: float, last_known_price: float, dry_run: bool = False) -> Tuple[Optional[str], Optional[str]]`: Attempts to execute a sell (for TP/SL triggered by `PositionMonitor`). Returns status and identifier similar to `execute_buy`.
        *   (Optional) `get_trade_status(self, identifier: str)`: Method to check the status of a trade initiated via the provider (might be needed for Sniperoo).

2.  **Self-Built Execution Provider Implementation (`src/execution_providers/self_built.py`):**
    *   Create `SelfBuiltProvider` class inheriting from `ExecutionProvider`.
    *   Implement `initialize`: Store `SolanaClient`, `DatabaseManager`, and load relevant `self_built_settings` from the passed config.
    *   Implement `async execute_buy`:
        *   Log intent, check `dry_run`.
        *   Load parameters from `self_built_settings` (slippage, priority fee strategy/value, Jito settings).
        *   Use `SolanaClient` to:
            *   Fetch pool keys/info if needed (or assume passed if filter service provides).
            *   Calculate minimum amount out based on slippage.
            *   Build swap instruction using target DEX program ID.
            *   Build transaction, add priority fee/Jito tip instructions.
            *   Call `SolanaClient.create_sign_send_transaction` (respecting `dry_run`).
        *   If not `dry_run`, monitor confirmation via `SolanaClient.confirm_transaction`.
        *   Return appropriate `(status, signature)` tuple based on success, failure, or simulation.
    *   Implement `async execute_sell`: Similar logic for building/sending the sell transaction. Load sell-specific config (slippage, fees).
    *   Handle errors from `SolanaClient` gracefully, returning 'FAILED' status.

3.  **Sniperoo API Execution Provider Implementation (`src/execution_providers/sniperoo.py`) - Optional:**
    *   Create `SniperooProvider` class inheriting from `ExecutionProvider`.
    *   Implement `initialize`: Store `HttpClient`, `DatabaseManager`, load `sniperoo_api_settings` (endpoint, key env var), load API key from secrets.
    *   Implement `async execute_buy`:
        *   Log intent, check `dry_run`.
        *   Format the request body JSON according to Sniperoo API docs, including token mint, amount, and auto-sell parameters (`auto_sell_enabled`, `tp_pct`, `sl_pct`) loaded from config.
        *   Use `HttpClient` to make the authenticated POST request.
        *   Handle API response (success, specific errors, rate limits).
        *   Return appropriate `(status, identifier)` tuple (e.g., 'SUCCESS', 'sniperoo_trade_id_123' or 'FAILED', None).
    *   Implement `async execute_sell`: Only needed if `config.sniperoo_api_settings.auto_sell_enabled` is `False`. Implement call to Sniperoo's sell endpoint (if it exists).

4.  **Execution Service Implementation (`src/services/execution_service.py`):**
    *   Create `ExecutionService` class.
    *   Initialize with `DatabaseManager`, config, secrets, and shared clients (`SolanaClient`, `HttpClient`).
    *   **Dynamically Load Provider:** In `initialize` or `run` setup:
        *   Read `config.execution.provider`.
        *   If "SELF_BUILT", instantiate `SelfBuiltProvider`, passing dependencies.
        *   If "SNIPEROO_API", instantiate `SniperooProvider`, passing dependencies.
        *   Store the instantiated provider instance (e.g., `self.provider`).
    *   Implement `async run(self, input_queue: asyncio.Queue)`:
        *   Consume validated filter data (`token_mint`, `lp_address`, ...) from the filter queue.
        *   Load shared `buy_amount_sol` from config.
        *   Call `status, identifier = await self.provider.execute_buy(...)`, passing necessary data and the global `dry_run` flag.
        *   Log the outcome.
        *   **Update DB:** If status indicates success ('SUCCESS' or 'SIMULATED_SUCCESS'), call `DatabaseManager.add_position(...)` using the returned identifier (signature or trade ID). If 'FAILED', potentially update detection status to 'BUY_FAILED'.

5.  **Position Monitoring Service Implementation (`src/services/monitoring_service.py`):**
    *   Create `MonitoringService` class.
    *   Initialize with `ExecutionService` (or directly with the loaded execution provider), `DatabaseManager`, `HttpClient` (for API price checks), `SolanaClient` (for RPC price checks), and config.
    *   Implement `async run(self)`:
        *   Main loop controlled by `config.monitoring.enabled`. **Crucially, also check `config.execution.provider` and potentially `config.sniperoo_api_settings.auto_sell_enabled` to determine if this service *should* run.** (Skip loop if Sniperoo handles auto-sell).
        *   Inside loop: `await asyncio.sleep(config.monitoring.price_poll_interval_seconds)`.
        *   Fetch active positions: `positions = await self.db_manager.get_all_active_positions()`.
        *   For each `position` in `positions`:
            *   Call `_check_position(position)`.
    *   Implement `async _check_position(self, position)`:
        *   Fetch current price using the method defined in `config.monitoring.price_provider`:
            *   If "RPC_POOL_CHECK": Use `SolanaClient` to get pool reserves and calculate price. Handle potential errors (pool drained?).
            *   If "DEXSCREENER_API" / "BIRDEYE_API": Use `HttpClient` to call the respective API endpoint. Handle rate limits and errors. Use free tier cautiously.
        *   If price fetch fails, log error and potentially skip checks for this cycle.
        *   Calculate current P&L %.
        *   **Check Exit Conditions:**
            *   If `price >= position.entry_price * (1 + config.monitoring.take_profit_pct / 100)` -> Trigger Sell (TP).
            *   If `price <= position.entry_price * (1 - config.monitoring.stop_loss_pct / 100)` -> Trigger Sell (SL).
            *   If `config.monitoring.enable_time_stop` and `time_elapsed > config.monitoring.time_stop_minutes * 60` -> Trigger Sell (Time).
        *   **Trigger Sell:** If an exit condition is met:
            *   Log the reason (TP/SL/Time).
            *   Prevent duplicate sell attempts for the same position (use status in DB or in-memory set). Update position status in DB to 'SELL_PENDING'.
            *   Call `status, identifier = await self.execution_provider.execute_sell(...)`, passing position details and `dry_run` flag.
            *   Log sell attempt outcome. (Actual move to history happens on confirmation - potentially handled by execution provider callback or a separate confirmation checker task).

**Key Considerations:**

*   **Modularity:** The `ExecutionProvider` interface enforces separation, allowing easy switching or addition of new execution methods.
*   **Configuration:** All behavior (provider choice, fees, slippage, TP/SL levels, polling intervals, auto-sell flags) is driven by `config.yml`.
*   **State Management:** Interactions with the database (`DatabaseManager`) are crucial for tracking positions and preventing duplicate actions. The transition from `positions` to `trades` needs careful handling, potentially after sell confirmation.
*   **Error Handling:** Robust handling of errors during transaction building, sending, confirmation, API calls, and price fetching is essential.
*   **Monitoring Logic:** The decision of *whether* the `MonitoringService` needs to actively manage sells depends heavily on the chosen execution provider and its capabilities (e.g., Sniperoo's auto-sell). The main loop needs to check this.

**Expected Deliverables:**

*   Defined `ExecutionProvider` interface.
*   Functional and unit-tested `SelfBuiltProvider` for buy/sell using `SolanaClient`.
*   (Optional) Functional and unit-tested `SniperooProvider` for buy (and maybe sell) using `HttpClient`.
*   Functional and unit-tested `ExecutionService` capable of dynamically loading and using the selected provider.
*   Functional and unit-tested `MonitoringService` capable of fetching positions, polling prices (via configured method), checking TP/SL/Time conditions based on config, and triggering sells via the `ExecutionService`/provider.