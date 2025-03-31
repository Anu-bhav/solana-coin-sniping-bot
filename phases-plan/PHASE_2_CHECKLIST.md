# Phase 2 Checklist: Detection & Filtering Services Implementation

**Goal:** Verify the implementation and unit testing of the `DetectionService`, `FilterService`, and associated state/DB interactions. Ensure filters operate based on configuration and handle errors/limits appropriately.

**Detection Service (`DetectionService`):**

*   [ ] Implement `DetectionService` class structure.
*   [ ] Implement initialization loading config (Program IDs, Base Mints, etc.) and dependencies (`SolanaClient`, `DatabaseManager`).
*   [ ] Implement `async run()` method with main WSS connection loop.
    *   [ ] Test basic loop structure (mock sleep/connection).
*   [ ] Implement WSS connection logic using `SolanaClient.start_log_subscription`.
    *   [ ] Test subscription call with correct Program IDs from config.
*   [ ] Implement WSS reconnection logic using config delay.
    *   [ ] Test reconnection attempt after simulated close/error.
*   [ ] Implement `async _handle_log_message()` callback.
    *   [ ] Test handling of non-log messages (e.g., subscription confirmations).
    *   [ ] Test extraction of transaction signature from valid log messages.
*   [ ] Implement Log Parsing Logic:
    *   [ ] Test calling `SolanaClient.getParsedTransaction` (mocked).
    *   [ ] **Testing:** Unit test parsing logic with various sample Devnet `Initialize` log structures (success, potential variations) to reliably extract `new_token_mint`, `base_token_mint`, `lp_address`, and `creator_address` (if possible). Test handling of non-Initialize logs.
*   [ ] Implement Initial Source Filtering:
    *   [ ] Test check against `config.detection.target_base_mints`.
    *   [ ] Test discarding non-target pairs.
*   [ ] Implement Duplicate Detection Check:
    *   [ ] Test calling `DatabaseManager.check_if_token_processed` (mocked).
    *   [ ] Test discarding already processed tokens.
*   [ ] Implement Queueing Logic:
    *   [ ] Test putting correctly formatted data onto the output queue (mocked queue).
*   [ ] Implement State Update Logic:
    *   [ ] Test calling `DatabaseManager.add_detection` with correct status ('PENDING_FILTER') and data. Verify UPSERT behavior conceptually or via mock.
*   [ ] Ensure robust error handling within the callback (parsing, RPC calls). Log errors appropriately.

**State Tracker / Database Manager:**

*   [ ] Confirm `DatabaseManager` includes functions needed by `DetectionService` and `FilterService` (`add_detection`, `update_detection_status`, `check_if_token_processed`, `check_if_creator_processed`).
*   [ ] Ensure necessary parameters (e.g., `creator_address`) are added to relevant DB functions and schema if needed for duplicate checks.

**Filter Service (`FilterService`):**

*   [ ] Implement `FilterService` class structure.
*   [ ] Implement initialization loading config (`filtering` section) and dependencies (`SolanaClient`, `HttpClient`, `DatabaseManager`).
*   [ ] Implement `async run()` method consuming from input queue.
    *   [ ] Test basic loop structure (mock queue).
*   [ ] Implement `async _run_filter_pipeline()` orchestrator function.
    *   [ ] Test calling individual filter group helper methods.
    *   [ ] Test aggregation of results logic.
    *   [ ] Test calling `DatabaseManager.update_detection_status` with final status/reason (mocked).
    *   [ ] Test queueing passed candidates to the output queue (mocked).
    *   [ ] Test error handling around filter group calls.
*   **Testing:** For EACH Filter Group Helper (`_run_contract_liquidity_checks`, `_run_metadata_distribution_checks`, etc.):
    *   [ ] **Unit Test:** Check the main `enabled` flag from config. Verify it skips if disabled.
    *   [ ] **Unit Test:** For EACH Sub-Filter within the group:
        *   [ ] Check the specific sub-filter `enabled` flag from config. Verify skip if disabled.
        *   [ ] Mock client calls (`SolanaClient`, `HttpClient`) needed for the check.
        *   [ ] Test the filter logic against mocked successful responses (should pass).
        *   [ ] Test the filter logic against mocked responses that should cause failure based on config thresholds (should fail with correct reason).
        *   [ ] Test handling of client errors (e.g., RPC timeout, API 404) - should likely result in filter failure/error status.
        *   [ ] Test handling of API rate limits (HTTP 429) - should likely result in filter failure/error status or implement retry based on config.
        *   [ ] Verify parameters (thresholds, provider choices) are correctly read from the injected config object.
*   **Testing:** Implement `_run_duplicate_history_checks` logic.
    *   [ ] Unit test calling `DatabaseManager` functions (mocked).
    *   [ ] Test pass/fail logic based on DB response and config flags (`block_returning...`).
*   Ensure filter results (`passed: bool, reason: str`) are returned correctly.
*   Ensure state updates via `DatabaseManager` reflect filter outcomes accurately.

**General:**

*   [ ] Review code for clarity, error handling, and adherence to async best practices.
*   [ ] Ensure logging within services provides sufficient context for debugging.
*   [ ] Run Linter/Formatter on new code.
*   [ ] Commit tested code to Git frequently using feature branches.

**Completion:**

*   [ ] All items above checked.
*   [ ] All new code is unit tested.
*   [ ] Phase 2 deliverables are ready and committed to Git. Integration testing will occur in Phase 4.