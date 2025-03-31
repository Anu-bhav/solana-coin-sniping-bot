# Phase 4 Checklist: Integration, System Testing & Safety Protocols

**Goal:** Verify the complete application integrates correctly, functions as expected end-to-end on Devnet, and identify any remaining issues before Mainnet consideration.

**Logging:**

*   [ ] Review logs from all modules. Ensure sufficient context and clarity.
*   [ ] Verify structured logging (JSON) works as configured.
*   [ ] Verify log file rotation/retention works based on config (may require running longer tests or manual checks).

**Main Application Integration (`main.py`):**

*   [ ] Implement main `async def main()` entry point.
*   [ ] Test config loading and validation on startup (catches bad config).
*   [ ] Test initialization of DB, Clients, Services, passing config/dependencies correctly.
*   [ ] Test dynamic loading of the configured Execution Provider.
*   [ ] Test creation and management of `asyncio` Queues and Tasks.
*   [ ] Implement and test Graceful Shutdown logic (handles Ctrl+C / SIGTERM). Verify connections (WSS, DB, HTTP Session) are closed.

**Integration Testing (Code Level):**

*   [ ] Write integration tests verifying data flow: Detection Queue -> Filter Service -> Execution Queue -> Execution Service -> Provider call (mocked).
*   [ ] Write integration tests verifying state updates via `DatabaseManager` (mocked) triggered by different services.

**End-to-End Devnet Testing (`dry_run=True`):**

*   [ ] Setup environment: Run `main.py` with `APP_ENV=development`, `dry_run=True` in `config.yml`. Connect to Devnet WSS/RPC/APIs.
*   [ ] Verify successful WSS connection and `logsSubscribe` setup in logs.
*   [ ] Monitor logs for detection events from live Devnet activity.
*   [ ] Verify Filter Service processes detected events. Check logs for filter pass/fail reasons matching expectations for Devnet tokens.
*   [ ] Verify `detections` table in SQLite DB is updated correctly.
*   [ ] Verify *simulated* buy logs appear for passed tokens.
*   [ ] Verify *simulated* sell logs appear if monitoring active and conditions met.
*   [ ] Run for extended duration (hours/days) and check for stability, memory leaks, unhandled errors.

**End-to-End Devnet Testing (`dry_run=False` - Live Devnet SOL):**

*   [ ] Setup environment: `APP_ENV=development`, **`dry_run=False`**, low `buy_amount_sol`. Fund Devnet wallet.
*   [ ] **Create & Run Test Scenarios on Devnet:**
    *   [ ] Test "Good Token" scenario (should detect, filter pass, buy execute, monitor, TP/SL execute).
    *   [ ] Test "Bad Authority Token" scenario (should detect, filter fail at Contract Security check).
    *   [ ] Test "Bad LP Token" scenario (should detect, filter fail at LP Status check).
    *   [ ] Test "No Socials Token" scenario (should detect, filter fail at Metadata check if enabled).
    *   [ ] Test "Duplicate Token/Creator" scenario (should detect, filter fail at Duplicate check if enabled).
*   **Verification Steps for Each Scenario:**
    *   [ ] Monitor Bot Logs for correct detection & filtering decisions.
    *   [ ] Monitor SQLite DB for correct status updates (`detections`, `positions`, `trades`).
    *   [ ] **Monitor Solscan Devnet** to verify actual BUY/SELL transactions sent/confirmed/failed. Check fees/slippage.
*   **Test Both Execution Providers:** If `SniperooProvider` implemented, repeat relevant E2E tests with `execution.provider: SNIPEROO_API` in config (may require Sniperoo test setup).
*   **Test Robustness:**
    *   [ ] Test manual stop/restart (verify state recovery from DB).
    *   [ ] Test handling of simulated WSS disconnect/reconnect.
    *   [ ] Test behavior under simulated high volume / potential rate limiting (if possible to trigger on Devnet).

**Code Review & Refinement:**

*   [ ] Conduct final code review (focus: correctness, security, errors, async).
*   [ ] Refactor code based on test findings and review feedback.
*   [ ] Update README with setup/run instructions and configuration details.
*   [ ] Ensure all tests (Unit, Integration) are passing after refactoring.

**Completion:**

*   [ ] All items above checked.
*   [ ] Document results, key findings, and known limitations from Devnet E2E testing.
*   [ ] Make a go/no-go decision for proceeding to Phase 5 based *only* on successful and well-understood Devnet performance.
*   [ ] Phase 4 deliverables are ready and committed to Git.