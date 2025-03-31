# Phase 0: Strategic Foundation & Prerequisite Setup

**Goal:** Establish a rock-solid foundation for the project by defining scope, setting up the development environment, researching core technologies, implementing secure configuration management, and ensuring all prerequisites are met before writing core bot logic.

**Duration Estimate:** 1 Week

**Key Activities & Actions:**

1.  **Scope & Constraint Finalization:**
    *   Formally document the target ecosystem (Solana Pump.fun -> Raydium/PumpSwap), bot type (Sniper+Manager), core language (Python 3.9+), and primary architectural patterns (`asyncio`, modular services).
    *   Explicitly state the constraint: Devnet-first development, maximize free-tier resource usage initially, plan for strategic paid upgrades (starting with RPC), secrets via `.env`, non-secrets via `config.yml`.
    *   Define initial success criteria for Devnet testing (e.g., reliably detect, filter based on basic checks, execute simulated/real Devnet trades, manage state via DB).

2.  **In-Depth Research:**
    *   **Solana:** Refresh/deepen understanding of Accounts, Transactions, Instructions, Programs (SPL Token, Associated Token Account, Compute Budget), RPC/WSS methods, Priority Fees, potential impact of network congestion/fees on Devnet vs. Mainnet.
    *   **Pump.fun:** Study the latest graduation mechanics, typical MC thresholds, common contract patterns or deployer behaviors.
    *   **Target DEX (Devnet):** Use Solscan/SolanaFM on Devnet to find the **exact Program IDs** for Raydium Liquidity Pool v4 and/or PumpSwap's AMM. Analyze recent `Initialize` and `Swap` transactions to understand required accounts and instruction data formats. Document these findings meticulously.
    *   **Scam Vectors:** Compile a list of common scam types on Solana (honeypots, LP rugs, disabled trading, mint authority abuse, distribution manipulation) and brainstorm how filters might detect them (even if implementation is deferred).

3.  **Technology Stack Installation & Verification:**
    *   Setup Python 3.9+ environment (recommend `venv`).
    *   Initialize Git repository with a proper `.gitignore` (including `.env*`, `__pycache__`, etc.).
    *   Install core dependencies: `pip install solana aiohttp websockets aiosqlite python-dotenv pyyaml pydantic structlog pytest pytest-asyncio ruff black` (or similar linter/formatter).
    *   Generate and commit initial `requirements.txt` or `pyproject.toml`.
    *   Verify installations by running basic imports in a Python interpreter.

4.  **Infrastructure Setup (Devnet Focus):**
    *   Generate a **NEW** dedicated Solana wallet specifically for **Devnet** testing. Securely store the private key.
    *   Create `.env.dev` and add the `DEV_WALLET_PRIVATE_KEY`.
    *   Obtain ample Devnet SOL using a reliable faucet (`solfaucet.com`, `solana airdrop` command) and verify balance.
    *   Sign up for **Free Tiers** at QuickNode and Helius. Obtain Devnet HTTP and WSS RPC URLs. Add these URLs to `.env.dev` (or directly in `config.yml` if they contain no secrets). Obtain API Keys if provided/needed for free tier access and add `HELIUS_API_KEY` (etc.) to `.env.dev`.
    *   Sign up for Free Tiers at DexScreener and Birdeye (if API keys are offered). Add keys to `.env.dev`.
    *   Define the initial `config/config.yml` structure (as per v1.5 example), including sections for `general`, `rpc`, `api_keys`, `detection`, `filtering` (with descriptive group names), `execution`, `monitoring`, `database`, `logging`. Populate with sensible Devnet defaults and placeholders. Commit `config.yml`.

5.  **Configuration Loading & Validation Implementation:**
    *   Implement `src/config/loader.py`.
    *   Define detailed `pydantic` models in `src/core/models.py` reflecting the *entire* expected structure of `config.yml`, including types and basic constraints (e.g., `int > 0`).
    *   The loader function should:
        *   Read `APP_ENV` (defaulting to `development`).
        *   Load the corresponding `.env` file (`.env.dev` or `.env.prod`) using `python-dotenv`. Access secrets via `os.getenv()`.
        *   Load `config/config.yml` using `PyYAML`.
        *   Merge secrets into the loaded config structure where specified (e.g., replacing placeholders like `mainnet_http_url_env_var`).
        *   **Validate the entire merged structure against the `pydantic` models.** Raise specific `ValidationError` on failure.
        *   Return the validated `pydantic` config object.

6.  **Logging Setup:**
    *   Implement `src/core/logger.py`.
    *   Configure `structlog` based on settings loaded from the config object (level, file path, format). Ensure it's easy to initialize and use throughout the application.

7.  **Project Structure Creation:**
    *   Create the directory structure outlined in v1.5. Add `__init__.py` files where necessary.

**Key Considerations:**

*   **Security:** Handling of private keys and API keys via `.env` is paramount. Never commit secrets.
*   **Config Validation:** Robust `pydantic` validation catches errors early, preventing runtime failures due to bad configuration.
*   **Devnet Focus:** All RPC endpoints, Program IDs, wallet keys, and testing are strictly confined to Devnet during this phase.
*   **Clarity:** Ensure `config.yml` uses descriptive names as planned.

**Expected Deliverables:**

*   Initialized Git repository with project structure.
*   Installed dependencies.
*   Generated Devnet wallet with SOL.
*   Populated `.env.dev` (secrets) and `config/config.yml` (parameters).
*   Functional and tested configuration loader (`src/config/loader.py`) with `pydantic` validation.
*   Functional logger setup (`src/core/logger.py`).
*   Documented findings from research (especially Devnet Program IDs and DEX instruction formats).