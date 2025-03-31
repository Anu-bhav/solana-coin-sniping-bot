# Phase 3 Checklist: Execution & Position Management Implementation

**Goal:** Verify the implementation and unit testing of the modular execution system (`ExecutionProvider` interface, `SelfBuiltProvider`, optional `SniperooProvider`, `ExecutionService`) and the `MonitoringService`.

**Execution Provider Interface (`ExecutionProvider`):**

*   [ ] Define `ExecutionProvider` ABC or Protocol in `src/execution_providers/base.py`.
*   [ ] Define abstract methods: `initialize`, `execute_buy`, `execute_sell`, potentially `get_trade_status`. Ensure clear method signatures and return types (e.g., `Tuple[Optional[str], Optional[str]]` for status/identifier).

**Self-Built Execution Provider (`SelfBuiltProvider`):**

*   [ ] Implement `SelfBuiltProvider` class inheriting from `ExecutionProvider`.
*   [ ] Implement `initialize` storing dependencies (`SolanaClient`, `DatabaseManager`) and loading `self_built_settings` from config.
*   [ ] Implement `async execute_buy`:
    *   [ ] Test loading correct config (slippage, fees, jito).
    *   [ ] Test calling `SolanaClient` to build swap instruction.
    *   [ ] Test adding correct priority fee / Jito instructions based on config.
    *   [ ] Test calling `SolanaClient.create_sign_send_transaction`.
    *   [ ] **Testing:** Unit test `dry_run=True` behavior (returns 'SIMULATED_SUCCESS', None).
    *   [ ] **Testing:** Unit test `dry_run=False` path (mocks `SolanaClient.send/confirm`, returns 'SUCCESS'/'FAILED', mock signature).
    *   [ ] Test error handling from `SolanaClient` calls (returns 'FAILED', None).
*   [ ] Implement `async execute_sell`:
    *   [ ] Similar tests as `execute_buy` for sell logic.

**Sniperoo API Execution Provider (`SniperooProvider` - Optional):**

*   [ ] Implement `SniperooProvider` class inheriting from `ExecutionProvider`.
*   [ ] Implement `initialize` storing dependencies (`HttpClient`, `DatabaseManager`), loading `sniperoo_api_settings`, loading API key.
*   [ ] Implement `async execute_buy`:
    *   [ ] Test loading correct config (endpoint, auto-sell params).
    *   [ ] Test correct formatting of Sniperoo API request body based on config/inputs.
    *   [ ] Test calling `HttpClient.post` with correct URL, body, headers (Auth).
    *   [ ] **Testing:** Unit test `dry_run=True` behavior (returns 'SIMULATED_SUCCESS', None).
    *   [ ] **Testing:** Unit test `dry_run=False` path (mocks `HttpClient.post`, handles success/error responses, returns 'SUCCESS'/'FAILED', mock identifier).
    *   [ ] Test handling of specific Sniperoo API errors (mocked responses).
*   [ ] Implement `async execute_sell` (if needed based on config).
    *   [ ] Similar tests for sell API call.

**Execution Service (`ExecutionService`):**

*   [ ] Implement `ExecutionService` class.
*   [ ] Implement initialization loading config, dependencies.
*   [ ] Implement dynamic loading of the correct execution provider based on `config.execution.provider`.
    *   [ ] **Testing:** Unit test provider loading logic for both "SELF_BUILT" and "SNIPEROO_API" settings.
*   [ ] Implement `async run` consuming from filter queue.
*   [ ] Implement delegation to `self.provider.execute_buy`.
    *   [ ] **Testing:** Unit test calling the mocked provider's `execute_buy` with correct parameters and `dry_run` flag.
*   [ ] Implement DB update logic via `DatabaseManager` based on provider response.
    *   [ ] **Testing:** Unit test calling `DatabaseManager.add_position` (mocked) on successful buy status. Test handling of failed buy status.

**Position Monitoring Service (`MonitoringService`):**

*   [ ] Implement `MonitoringService` class.
*   [ ] Implement initialization loading config, dependencies (`ExecutionService`/provider, `DatabaseManager`, `HttpClient`, `SolanaClient`).
*   [ ] Implement `async run` method with main loop.
    *   [ ] Test check for `config.monitoring.enabled` and execution provider logic (should skip loop if monitoring not needed).
    *   [ ] Test `asyncio.sleep` with interval from config.
*   [ ] Implement fetching active positions via `DatabaseManager.get_all_active_positions`.
    *   [ ] **Testing:** Unit test loop iteration over mocked positions.
*   [ ] Implement `async _check_position`.
*   [ ] Implement price fetching logic based on `config.monitoring.price_provider`.
    *   [ ] **Testing:** Unit test RPC price check (mock `SolanaClient`).
    *   [ ] **Testing:** Unit test API price check (mock `HttpClient`, test rate limit handling).
    *   [ ] Test handling of price fetch errors.
*   [ ] Implement TP/SL/Time Stop condition checks using config thresholds.
    *   [ ] **Testing:** Unit test trigger logic for TP, SL, and Time Stop with various price/time inputs.
*   [ ] Implement sell trigger logic:
    *   [ ] Test updating position status to 'SELL_PENDING' via `DatabaseManager` (mocked).
    *   [ ] Test calling `self.execution_provider.execute_sell` (mocked) with correct parameters and `dry_run` flag.
    *   [ ] Test logic preventing duplicate sell attempts for the same position.

**General:**

*   [ ] Ensure consistent use of `dry_run` flag propagation.
*   [ ] Verify configuration values (fees, slippage, TP/SL) are correctly loaded and used.
*   [ ] Review code for clarity, error handling, async best practices.
*   [ ] Run Linter/Formatter.
*   [ ] Commit tested code to Git frequently.

**Completion:**

*   [ ] All items above checked.
*   [ ] All new code is unit tested.
*   [ ] Phase 3 deliverables are ready and committed to Git. Integration and E2E testing follow in Phase 4.