# Phase 1 Checklist: Core Clients & Database Implementation

**Goal:** Verify the successful implementation and unit testing of the fundamental interaction layers (`DatabaseManager`, `SolanaClient`, `HttpClient`).

**Database (`DatabaseManager` & `schema.sql`):**

*   [ ] Define `database/schema.sql` with tables: `detections`, `positions`, `trades`. Include correct types, PKs, indexes.
*   [x] Implement `DatabaseManager` class in `src/database/manager.py`.
*   [ ] Implement `__init__` loading DB path from config.
*   [ ] Implement `async initialize_db()` creating tables from schema.
    *   [ ] **Testing:** Unit test `initialize_db` (mock `aiosqlite`, check connection, check execute script called).
*   [x] Implement `async add_detection(...)`.
    *   [x] **Testing:** Unit test adding a new detection record.
*   [ ] Implement `async update_detection_status(...)`.
    *   [ ] **Testing:** Unit test updating status/reason for an existing detection.
*   [ ] Implement `async add_position(...)` (preferably using UPSERT).
    *   [ ] **Testing:** Unit test adding a new position. Test updating an existing position via UPSERT.
*   [ ] Implement `async update_position_status(...)`.
    *   [ ] **Testing:** Unit test updating position status.
*   [ ] Implement `async get_active_position(...)`.
    *   [ ] **Testing:** Unit test retrieving an existing position. Test retrieving non-existent position (returns None).
*   [ ] Implement `async get_all_active_positions()`.
    *   [ ] **Testing:** Unit test retrieving multiple positions. Test retrieving when none exist (returns empty list).
*   [ ] Implement `async move_position_to_trades(...)`.
    *   [ ] **Testing:** Unit test successful move (check delete from positions, insert into trades). Test handling if position doesn't exist. Ensure atomicity (mock transaction commit/rollback).
*   [ ] Implement `async check_if_token_processed(...)`.
    *   [ ] **Testing:** Unit test checking for existing processed token. Test checking non-existent token.
*   [ ] Implement `async check_if_creator_processed(...)`.
    *   [ ] **Testing:** Unit test checking for existing creator. Test checking non-existent creator.
*   [ ] Ensure all DB methods use `async`/`await` and `aiosqlite`.
*   [ ] Ensure basic DB error handling is present.

**Solana Client (`SolanaClient`):**

*   [ ] Implement `SolanaClient` class in `src/clients/solana_client.py`.
*   [ ] Implement `__init__` loading RPC URLs/timeout from config.
*   [ ] Implement `async connect_http()` and `async connect_wss()`.
    *   [ ] **Testing:** Unit test connection logic (mock `AsyncClient` init/connect). Test error handling.
*   [ ] Implement `async load_keypair()`.
    *   [ ] **Testing:** Unit test loading from a known private key string. Test handling invalid key format.
*   [ ] Implement RPC wrapper methods (`getBalance`, `getAccountInfo`, etc.).
    *   [ ] **Testing:** Unit test each wrapper: verify it calls the correct `AsyncClient` method with correct args, test return value handling, test error propagation (mock `AsyncClient` methods).
*   [ ] Implement `async get_account_info_decoded()` with parsing for Mint/TokenAccount.
    *   [ ] **Testing:** Unit test parsing logic with sample raw account data for Mint and TokenAccount. Test handling unknown account types.
*   [ ] Implement `async build_swap_instruction()` for Devnet DEX IDs.
    *   [ ] **Testing:** Unit test instruction building: verify Program ID, accounts (correct keys, is_signer, is_writable), and data serialization match expected format based on research. Test with different input amounts/slippage.
*   [<em> </em>] Implement `async create_sign_send_transaction()`.
    *   [ ] Add Compute Budget instructions.
    *   [ ] **Testing:** Unit test TX construction (verify instructions, blockhash, fee payer, signatures). Test sending logic (mock `send_transaction`). Test retry logic if implemented.
    *   [ ] **Testing:** Explicitly test `dry_run=True` behavior (logs intent, returns simulated value, does NOT call `send_transaction`).
    *   [ ] **Testing:** Explicitly test `dry_run=False` behavior (calls `send_transaction`).
*   [ ] Implement `async confirm_transaction()`.
    *   [ ] **Testing:** Unit test confirmation logic (mock `confirm_transaction`). Test handling different confirmation statuses.
*   [ ] Implement `async start_log_subscription()` and `async close_wss_connection()`.
    *   [ ] **Testing:** Unit test subscription logic (mock WSS connection/methods). Verify correct Program ID/commitment used. Test connection closing.
*   [ ] Ensure all methods use `async`/`await` and `solana-py`'s async client.
*   [ ] Ensure basic RPC error handling/logging is present.

**HTTP Client (`HttpClient`):**

*   [ ] Implement `HttpClient` class in `src/clients/http_client.py`.
*   [ ] Implement `__init__` creating/managing `aiohttp.ClientSession`. Load timeout from config. Load API keys from secrets via config loader.
*   [ ] Implement generic `async request()` method.
*   [ ] Implement handling of methods (GET/POST), headers (API keys), params, JSON body.
*   [ ] Implement error handling for status codes (4xx, 5xx).
*   [ ] Implement specific handling for 429 Rate Limit (delay/retry based on config).
*   [ ] Implement handling for connection errors/timeouts.
*   [ ] Implement convenience methods (`get`, `post`).
*   [ ] **Testing:** Unit test `request` method using mocked `aiohttp.ClientSession` responses:
    *   [ ] Test successful GET/POST requests.
    *   [ ] Test correct header injection (API keys).
    *   [ ] Test handling of 404 Not Found.
    *   [ ] Test handling of 500 Server Error.
    *   [ ] Test handling of 429 Rate Limit (verify retry/delay logic based on config).
    *   [ ] Test handling of connection errors/timeouts.

**Completion:**

*   [ ] All items above checked.
*   [ ] All implemented code is unit tested.
*   [x] Phase 1 deliverables are ready and committed to Git.