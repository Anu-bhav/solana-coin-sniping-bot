# Phase 1: Core Clients & Database Implementation

**Goal:** Build and thoroughly test the fundamental interaction layers: the Solana RPC/WSS client, the external HTTP API client, and the database management layer for state persistence. These modules will form the bedrock upon which all other services are built.

**Duration Estimate:** 2-3 Weeks

**Key Activities & Actions:**

1.  **Database Schema & Manager Implementation:**
    *   Create `database/schema.sql`. Define the precise `CREATE TABLE` statements for `detections`, `positions`, and `trades`, including appropriate column types (TEXT, REAL, INTEGER, TIMESTAMP), primary keys, foreign keys (if applicable), and indexes (e.g., on `token_mint`, `status`, timestamps) for efficient querying.
    *   Implement the `DatabaseManager` class in `src/database/manager.py`.
        *   Use `aiosqlite` for all database operations.
        *   Load the correct database file path (`devnet_db_config.db_file` or `mainnet_db_config.db_file`) from the validated config object based on `APP_ENV`.
        *   Implement `async def initialize_db(self)`: Connects to the SQLite file (creating it if it doesn't exist) and executes the `schema.sql` script to create tables if they don't exist. Handle potential file path issues.
        *   Implement core asynchronous CRUD functions:
            *   `add_detection(token_mint, lp_address, base_mint, ...)`
            *   `update_detection_status(token_mint, status, reason)`
            *   `add_position(token_mint, entry_price, amount, ...)` (Consider using UPSERT: `INSERT...ON CONFLICT(token_mint) DO UPDATE...`)
            *   `update_position_status(position_id or token_mint, status)`
            *   `get_active_position(token_mint)` -> returns position details or None.
            *   `get_all_active_positions()` -> returns list of active positions.
            *   `move_position_to_trades(position_id or token_mint, exit_price, exit_reason, ...)` -> Deletes from `positions`, inserts into `trades`. Wrap in a transaction.
            *   `check_if_token_processed(token_mint)` -> Check `detections` table status.
            *   `check_if_creator_processed(creator_address)` -> Requires storing creator in `detections`, query based on that.
        *   Ensure proper error handling for database operations (e.g., catching `sqlite3.Error`).
        *   Use context managers (`async with connection...`) for managing connections and cursors.

2.  **Solana Client Implementation:**
    *   Implement the `SolanaClient` class in `src/clients/solana_client.py`.
    *   Initialize with the validated config object to get RPC URLs and timeout settings.
    *   Implement connection logic (`connect_http`, `connect_wss`) using `solana.rpc.api.AsyncClient` and WebSocket connections. Handle connection errors.
    *   Implement `load_keypair` from the private key loaded securely via the config loader.
    *   Implement wrappers for essential RPC calls (`getBalance`, `getAccountInfo`, `getLatestBlockhash`, `getTokenSupply`, `getTokenAccountBalance`, `getParsedTransaction`, etc.) using the async client. Add error handling and potentially basic retry logic (respecting config settings). Implement decoding for common account types (Mint, TokenAccount) using `solders` or `solana-py` helpers within `get_account_info_decoded`.
    *   Implement `build_swap_instruction` specific to **Devnet** Raydium/PumpSwap Program IDs and instruction formats identified in Phase 0 research. Parameterize amounts, slippage (calculate min_out), accounts.
    *   Implement `create_sign_send_transaction`:
        *   Takes list of instructions, signers (including bot keypair).
        *   Fetches recent blockhash.
        *   Adds Compute Budget instructions (`set_compute_unit_limit` - set reasonably high, `set_compute_unit_price` - load from config).
        *   Constructs `Transaction`, signs, serializes.
        *   Checks `dry_run` flag: If true, log intent and return simulated success/failure/signature based on config or simple logic.
        *   If false, call `self.async_client.send_transaction` with options (e.g., `skip_preflight=True` maybe configurable later). Handle send errors.
    *   Implement `confirm_transaction` using `self.async_client.confirm_transaction` with appropriate commitment level and timeout.
    *   Implement `start_log_subscription` wrapper for `logsSubscribe`, handling subscription confirmation and message routing (e.g., via an async callback or queue).
    *   Implement `close_wss_connection`.

3.  **HTTP Client Implementation:**
    *   Implement the `HttpClient` class in `src/clients/http_client.py`.
    *   Initialize with `aiohttp.ClientSession` (create one session per instance or pass one in). Load API Keys securely via config loader. Load request timeout from config.
    *   Implement generic `async def request(self, method, url, headers=None, params=None, json=None)` method.
    *   Inside `request`, handle:
        *   Adding API keys to headers (e.g., `Authorization: Bearer {key}`).
        *   Making the request using the `aiohttp` session.
        *   Handling specific HTTP errors (4xx, 5xx) including 429 (Rate Limit). Implement retry logic based on `config.rpc.enable_rate_limit_handling`, `rate_limit_delay_seconds`, `rate_limit_max_retries`.
        *   Handling connection errors and timeouts.
        *   Parsing JSON response or returning raw response if needed.
    *   Provide convenience methods like `async def get(...)` and `async def post(...)`.

**Key Considerations:**

*   **Asynchronicity:** All I/O operations (DB, RPC, HTTP) MUST be `async` using `aiosqlite`, `solana-py`'s async client, and `aiohttp`.
*   **Error Handling:** Implement robust error handling and logging in all client/DB interactions. What happens if an RPC call fails? If the DB is locked? If an API returns an unexpected format?
*   **Configuration Usage:** Ensure all relevant parameters (URLs, timeouts, keys, DB paths) are loaded from the validated config object.
*   **Resource Management:** Ensure database connections and `aiohttp` sessions are managed correctly (e.g., closed on shutdown).
*   **Devnet Focus:** All Program IDs, RPC endpoints used must be for Devnet.

**Expected Deliverables:**

*   Functional and unit-tested `DatabaseManager` capable of all required CRUD operations on the SQLite DB using `aiosqlite`.
*   Functional and unit-tested `SolanaClient` capable of connecting to Devnet RPC/WSS, fetching data, building/signing/sending transactions (respecting `dry_run`), and handling WSS subscriptions.
*   Functional and unit-tested `HttpClient` capable of making async REST API calls, handling authentication, errors, and rate limits using `aiohttp`.
*   Completed `database/schema.sql`.