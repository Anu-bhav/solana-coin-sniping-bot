# Phase 2: Detection & Filtering Services Implementation

**Goal:** Implement the core logic for automatically detecting new Pump.fun liquidity events and applying the configured filtering pipeline to identify potential snipe candidates. This phase heavily integrates the clients and database manager built in Phase 1.

**Duration Estimate:** 4-5 Weeks

**Key Activities & Actions:**

1.  **Detection Service Implementation (`src/services/detection_service.py`):**
    *   Create the `DetectionService` class.
    *   Initialize with `SolanaClient`, `DatabaseManager`, and the validated config object. Load relevant `detection` config settings (Program IDs for the current network, target base mints, reconnect delay).
    *   Implement `async run(self, output_queue: asyncio.Queue)` method:
        *   Contains the main loop for maintaining the WebSocket connection.
        *   Calls `self.solana_client.connect_wss()` if not connected.
        *   Calls `self.solana_client.start_log_subscription(self._handle_log_message)` targeting the configured Program IDs. Pass `_handle_log_message` as the async callback.
        *   Implement a loop with `asyncio.sleep` to keep the connection alive and handle reconnections using `config.detection.websocket_reconnect_delay_seconds` upon closure/error.
    *   Implement `async _handle_log_message(self, message)` callback:
        *   Parse the incoming WebSocket message. Check for subscription confirmations vs. actual log notifications. Handle potential errors in message format.
        *   If it's a log notification, extract the transaction signature.
        *   Use `self.solana_client.getParsedTransaction` (or similar to get detailed logs/accounts) for the signature. *Note: This is an RPC call triggered by a WSS message - monitor CU usage.*
        *   **Log Parsing Logic:** Implement detailed parsing of the transaction details (specifically looking for `Initialize` instruction logs from the target DEX Program ID) to reliably extract:
            *   `new_token_mint`: The address of the newly listed token.
            *   `base_token_mint`: The address of the other token in the pair (e.g., WSOL).
            *   `lp_address`: The address of the newly created liquidity pool account.
            *   `creator_address` (Attempt): Try to identify the transaction fee payer or relevant signer as the likely creator/deployer. This can be complex and might require analyzing instruction accounts. Store if found.
        *   **Initial Source Filtering:**
            *   Check if `base_token_mint` is in `config.detection.target_base_mints`. Discard if not.
            *   (Optional/Deferred) Check if `creator_address` matches Pump.fun deployer patterns (if known) or has a history related to Pump.fun.
        *   **Duplicate Detection Check:** Call `self.db_manager.check_if_token_processed(new_token_mint)`. If already processed (status != PENDING/NEW), log and discard.
        *   **Queueing:** If checks pass, add the detection details (`token_mint`, `lp_address`, `base_mint`, `creator_address` (optional)) to the `output_queue` for the Filter Service.
        *   **State Update:** Call `self.db_manager.add_detection(...)` to record the initial detection in the database with a 'PENDING_FILTER' status. Use UPSERT logic to avoid errors if detection is somehow duplicated rapidly.
    *   Implement proper error handling within the callback (parsing errors, RPC call errors).

2.  **State Tracker Module Enhancement (`src/core/state_tracker.py`):**
    *   (This module might be simple in-memory state or integrated directly within services interacting with `DatabaseManager`).
    *   If using in-memory state, ensure it's synchronized with the database periodically or on key events to prevent data loss on restarts. Define clear responsibility boundaries between in-memory state and persistent DB state. Consider if needed beyond direct DB interaction. *(Decision: Leaning towards direct DB interaction via `DatabaseManager` for simplicity and persistence, minimizing complex in-memory state.)*

3.  **Filter Service Implementation (`src/services/filter_service.py`):**
    *   Create the `FilterService` class.
    *   Initialize with `SolanaClient`, `HttpClient`, `DatabaseManager`, and the validated config object. Load the entire `filtering` section of the config.
    *   Implement `async run(self, input_queue: asyncio.Queue, output_queue: asyncio.Queue)` method:
        *   Continuously consumes detection data (`token_mint`, `lp_address`, ...) from the `input_queue`.
        *   For each candidate, execute the filtering pipeline asynchronously.
    *   Implement `async _run_filter_pipeline(self, detection_data)`:
        *   Log the start of filtering for the token.
        *   **Execute Filter Groups based on Config:** Call helper methods for each configured group. Use `try...except` blocks around groups/checks to handle errors gracefully and update DB status accordingly (e.g., 'FILTER_ERROR').
            *   `result1 = await self._run_contract_liquidity_checks(detection_data)`
            *   `result2 = await self._run_metadata_distribution_checks(detection_data)`
            *   `result3 = await self._run_trading_pattern_checks(detection_data)`
            *   `result4 = await self._run_duplicate_history_checks(detection_data)`
            *   `result5 = await self._run_external_rug_checks(detection_data)`
        *   **Aggregate Results:** Determine the final pass/fail status based on the results of enabled checks.
        *   **Update DB:** Call `self.db_manager.update_detection_status(token_mint, final_status, reason_string)`.
        *   **Queue for Execution:** If `final_status == 'PASSED'`, construct the necessary data payload (Token Mints, LP Address, maybe initial price estimate) and put it onto the `output_queue` for the Execution Service.
    *   **Implement Filter Group Helper Methods:** (e.g., `async _run_contract_liquidity_checks`)
        *   Check the main `enabled` flag for the group in the config. Return `(True, "SKIPPED")` if disabled.
        *   Inside each helper, check the `enabled` flag for *each specific sub-filter*.
        *   Call `SolanaClient` or `HttpClient` as needed, respecting config thresholds and provider choices.
        *   Handle API/RPC errors and rate limits gracefully (e.g., return `(False, "API_RATE_LIMIT")`).
        *   Return a tuple: `(passed: bool, reason: str)`. Aggregate reasons if multiple checks fail.
    *   **Implement Specific Filter Logic:** Write the detailed logic for each check outlined in the config (Mint/Freeze, LP Burn, Socials, Holder checks [minimal], Duplicate checks via DB, External Rug Check API call/parsing). Ensure all parameters are read from the config object.

**Key Considerations:**

*   **Concurrency & Rate Limits:** Filtering involves multiple async I/O calls (RPC, HTTP). Executing these fully concurrently might hit free-tier per-second limits. Implement careful concurrency management (e.g., using `asyncio.Semaphore` or processing checks semi-sequentially) if rate limiting becomes an issue during testing. Prioritize faster on-chain checks before potentially slower API calls.
*   **Error Handling:** Gracefully handle errors from RPC calls, API requests, log parsing, and DB interactions within both services. Log errors clearly and update detection status in the DB to 'FILTER_ERROR' or similar.
*   **State Consistency:** Ensure detected tokens are correctly logged in the DB and their status is updated reliably after filtering. Use UPSERT in `add_detection` to handle potential race conditions if the same token is detected multiple times quickly.
*   **Modularity:** Keep detection logic separate from filtering logic. Filters should be self-contained checks driven by config.
*   **Testability:** Design services and filter checks to be easily unit-testable by mocking client/DB dependencies and injecting config objects.

**Expected Deliverables:**

*   Functional and tested `DetectionService` capable of connecting to Devnet WSS, subscribing to logs, parsing pool creation events, performing basic source/duplicate checks, and queueing valid candidates while updating the DB.
*   Functional and tested `FilterService` capable of consuming candidates, executing the configured (minimal initial) filter pipeline using RPC/API clients, handling errors/rate limits, updating the DB with final filter status, and queueing passed candidates for execution.
*   Enhanced `DatabaseManager` with all necessary functions for detection/filtering state.
*   Comprehensive unit tests for both services and all individual filter logic functions.