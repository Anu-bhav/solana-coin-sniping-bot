# Phase 4: Integration, System Testing & Safety Protocols

**Goal:** Integrate all developed modules into a cohesive application, perform comprehensive end-to-end testing on Devnet (both simulated and live), refine logging, and establish safety protocols before considering Mainnet deployment.

**Duration Estimate:** 3-4 Weeks

**Key Activities & Actions:**

1.  **Logging Refinement (`src/core/logger.py` & Usage):**
    *   Review logging across all modules. Ensure critical actions, decisions, errors, and state changes are logged with sufficient context (e.g., token mint, transaction signature, filter results, error details, `dry_run` status, active provider).
    *   Use structured logging (`structlog`) consistently for easy parsing (JSON format configured).
    *   Implement log file rotation and retention based on `config.logging` settings.
    *   **Testing:** Manually review log output during integration/E2E tests to ensure clarity and completeness.

2.  **Main Application Integration (`src/main.py`):**
    *   Implement the main asynchronous entry point (`async def main()`).
    *   Load configuration using `config.loader`. Handle config validation errors gracefully on startup.
    *   Initialize `DatabaseManager` and call `initialize_db()`.
    *   Initialize shared clients (`SolanaClient`, `HttpClient`). Ensure `aiohttp.ClientSession` is created and eventually closed properly.
    *   Initialize core services (`DetectionService`, `FilterService`, `ExecutionService`, `MonitoringService`), passing validated config sections and dependencies. Ensure `ExecutionService` correctly instantiates the configured execution provider.
    *   Create `asyncio.Queue` instances for communication between services (Detection -> Filter -> Execution).
    *   Create `asyncio.Task` instances for the `run()` method of each active service (check config flags like `detection.enabled`, `monitoring.enabled`, and provider logic before starting monitor).
    *   Implement **Graceful Shutdown** logic:
        *   Use `signal.signal` (for `SIGINT`, `SIGTERM`) to trigger a shutdown sequence.
        *   In the shutdown sequence:
            *   Signal tasks to stop (e.g., using `asyncio.Event` or task cancellation).
            *   Wait for tasks to finish cleanly using `asyncio.gather` with `return_exceptions=True`.
            *   Close WebSocket connections (`SolanaClient.close_wss_connection`).
            *   Close `aiohttp.ClientSession`.
            *   Close Database connection.
            *   Log shutdown completion.

3.  **Integration Testing:**
    *   Focus on the interactions *between* modules within the running application context (but still potentially using mocks for external network/API calls initially).
    *   **Test Queue Data Flow:** Mock `DetectionService` to put known data on its output queue. Verify `FilterService` consumes it, processes it (mocking client calls), and puts expected data on the execution queue. Verify `ExecutionService` consumes it and calls the (mocked) execution provider.
    *   **Test State Updates:** Verify that service interactions correctly trigger state updates via `DatabaseManager` (mocked DB calls). E.g., Does `FilterService` update detection status? Does `ExecutionService` add a position on successful buy? Does `MonitoringService` trigger DB updates for sell attempts/completions?
    *   **Test Config Loading:** Verify different services receive and use the correct configuration sections passed during initialization.

4.  **End-to-End Devnet Testing (`dry_run=True`):**
    *   **Environment:** Run the complete `main.py` application on a stable machine (can be local dev machine initially). Set `APP_ENV=development`, ensure `.env.dev` and `config.yml` (with `dry_run: true`) are used. Connect to live Devnet RPC/WSS (Free Tier acceptable here).
    *   **Scenario:** Let the bot run and listen for *actual* Devnet pool creation events.
    *   **Verification:**
        *   Monitor logs intensively. Verify successful WSS connection and detection messages.
        *   Verify filter logic executes for detected tokens (check logs for pass/fail reasons based on Devnet data).
        *   Check SQLite DB (`detections` table) for status updates.
        *   Verify *simulated* buy logs appear from `ExecutionService`/provider for tokens passing filters.
        *   Verify *simulated* sell logs (TP/SL/Time) appear from `MonitoringService`/provider if simulated buys occur and monitoring is active.
        *   Check for unhandled errors, rate limit messages (from clients), unexpected behavior.
    *   **Duration:** Run for several hours or days to observe stability and handling of various Devnet events.

5.  **End-to-End Devnet Testing (`dry_run=False` - Live Devnet SOL):**
    *   **Environment:** Same as above, but set `dry_run: false` in `config.yml`. Ensure Devnet wallet has SOL. Set `buy_amount_sol` very low (e.g., 0.001).
    *   **Scenario Generation (Crucial):** Since Devnet activity might be sparse or not represent typical Mainnet launches, **actively create test scenarios:**
        *   Use Devnet tools/scripts (e.g., find a simple token creator UI for Devnet, use Solana CLI/JS scripts) to create new SPL tokens.
        *   Use Devnet tools (e.g., Raydium UI connected to Devnet, Orca Devnet UI, scripts using `solana-py`) to create new liquidity pools for your test tokens with varying characteristics:
            *   "Good": Revoked authorities, LP tokens manually burned to `111...` address, has basic metadata set.
            *   "Bad - Authority": Leave Mint/Freeze authority active.
            *   "Bad - LP": Don't burn LP tokens.
            *   "Bad - Filter": Create token designed to fail specific filters you implemented (e.g., high initial holder concentration if testing that).
    *   **Verification:**
        *   Run the bot. Observe if it correctly detects your test pools.
        *   Verify filtering decisions align with the test scenario characteristics and configured filters.
        *   **Check Solscan Devnet:** Verify if BUY transactions are actually sent for tokens that pass filters. Check confirmation status, fees paid, slippage incurred.
        *   **Check SQLite DB:** Verify `positions` table is updated correctly on successful buy.
        *   Let bot monitor positions. Simulate price changes (by manually swapping small amounts on Devnet DEX UI/scripts) to trigger TP/SL conditions.
        *   **Check Solscan Devnet:** Verify if SELL transactions (TP/SL/Time) are sent correctly. Check confirmation and P&L implications.
        *   **Check SQLite DB:** Verify positions are moved to `trades` table with correct exit details.
        *   Test BOTH execution providers (`SELF_BUILT`, `SNIPEROO_API` if implemented) thoroughly by changing config and rerunning tests.
    *   **Robustness Testing:** Manually stop/restart the bot during operation. Verify state is recovered correctly from the DB. Simulate WSS disconnects - verify reconnection. Send a high volume of test events - check for bottlenecks or rate limiting issues (even on Devnet free tiers).

6.  **Code Review & Refinement:**
    *   Perform a thorough code review focusing on: correctness, error handling, security (especially key handling, API interactions), configuration usage, adherence to async patterns, logging clarity, test coverage.
    *   Refactor code based on findings from testing and review to improve clarity, performance, and robustness. Update documentation/README.

**Key Considerations:**

*   **Test Coverage:** Aim for high unit test coverage, but recognize that E2E Devnet testing is essential for validating real-world interactions and timing.
*   **Devnet Limitations:** Devnet doesn't perfectly mirror Mainnet traffic, fees, or validator behavior. Some issues might only appear on Mainnet.
*   **Simulating Scams:** Be creative in setting up Devnet test scenarios to challenge your filters effectively.
*   **Iterative Debugging:** Expect to spend significant time debugging issues identified during E2E testing. Use detailed logging extensively.

**Expected Deliverables:**

*   Fully integrated application in `main.py`.
*   Refined and comprehensive logging across modules.
*   Completed Integration Tests verifying module interactions.
*   Documented results and logs from extensive E2E testing on Devnet (both `dry_run=True` and `dry_run=False` modes, testing various scenarios and both execution providers if applicable).
*   Code refactored based on testing and reviews.
*   Confidence (based on Devnet results) in the bot's core functionality, filtering logic (within free-tier limits), execution flow, state management, and error handling.
*   A clear list of known limitations or potential issues observed during Devnet testing (e.g., documented rate limit problems, filter weaknesses).