# Phase 0 Checklist: Strategic Foundation & Prerequisite Setup

**Goal:** Ensure all foundational elements are researched, set up, configured, and validated before core bot development begins.

**General:**

*   [x] Confirm understanding of Phase 0 Goals and Deliverables. *(Assumed complete via conversation)*
*   [ ] Document Scope & Constraints formally (in README or design doc). *(Partially done in README)*
*   [ ] Document initial Devnet Success Criteria. *(Deferred - Requires thought)*

**Research:**

*   [x] Document findings on Solana fundamentals (Accounts, TXs, Fees, etc.). *(User knowledge assumed)*
*   [x] Document findings on Pump.fun mechanics (Graduation, Contract Patterns). *(User knowledge assumed)*
*   [x] **Identify and Document precise Devnet Program IDs** for target DEX(s) (Raydium LP v4 / PumpSwap AMM). *(Research done, ID: DEVLej5U921Ld7ghS9aNfUMyfAAZGDpjp4z8BoBDL4 - Needs verification)*
*   [x] **Analyze and Document structure** of target DEX `Initialize` and `Swap` instructions on Devnet. *(Conceptual analysis done, details require SDK/IDL)*
*   [ ] Compile list of common Solana scam vectors and potential detection ideas. *(Deferred - For Filtering Phase)*

**Environment & Dependencies:**

*   [x] Install correct Python version (3.9+). *(User confirmed)*
*   [x] Create and activate Python virtual environment (`venv`).
*   [x] Initialize Git repository.
*   [x] Create comprehensive `.gitignore` file (including `.env*`, `__pycache__/`, `logs/`, `db/*.sqlite`).
*   [x] Install all dependencies listed in Tech Stack via `pip` (using `uv`).
*   [x] Generate and commit `requirements.txt` or `pyproject.toml`.
*   [x] Install and configure Linter (`ruff`) and Formatter (`black`). Run initial format/lint check.

**Infrastructure & Configuration:**

*   [x] Generate **new dedicated Devnet Solana wallet**. *(Manual Step - Pending)*
*   [x] Securely store Devnet private key in `.env.dev`. *(File created, user needs to add key)*
*   [ ] Fund Devnet wallet with sufficient SOL from a faucet. Verify balance. *(Manual Step - Pending)*
*   [x] Sign up for Free Tiers: QuickNode. *(Manual Step - Pending)*
*   [x] Sign up for Free Tiers: Helius. *(Manual Step - Pending)*
*   [x] Sign up for Free Tiers: DexScreener (if key offered). *(Manual Step - Pending)*
*   [x] Sign up for Free Tiers: Birdeye (if key offered). *(Manual Step - Pending)*
*   [x] Populate `.env.dev` with Devnet RPC URLs and any obtained API keys. *(File created, user needs to add details)*
*   [x] Create `config/config.yml` with the detailed structure from the plan. Populate with sensible Devnet defaults. Commit `config.yml`. *(File populated with template)*
*   [x] Implement `src/config/loader.py`.
    *   [x] Define comprehensive `pydantic` models for the entire config structure.
    *   [x] Implement loading of `.env` based on `APP_ENV`.
    *   [x] Implement loading of `config.yml`.
    *   [x] Implement merging/handling of secrets from `.env`.
    *   [x] Implement **rigorous validation** using `pydantic` models.
    *   [x] **Testing:** Write **unit tests** (`tests/config/test_loader.py`) for `loader.py`:
        *   [x] Test successful loading with valid Devnet config/env.
        *   [ ] Test successful loading with valid Prod config/env (using dummy prod env).
        *   [x] Test failure on missing `config.yml`.
        *   [x] Test failure on invalid YAML format.
        *   [x] Test failure on missing required fields in config (pydantic validation).
        *   [x] Test failure on incorrect data types in config (pydantic validation).
        *   [x] Test failure on missing required environment variables (`.env`).
        *   [x] Test correct environment variable override behavior.
        *   [ ] Test correct selection of network settings based on `APP_ENV`. *(Implicitly covered, could add explicit test later)*
*   [x] Implement `src/core/logger.py` using `structlog`.
    *   [x] Configure based on loaded config (level, file, format).
    *   [x] **Testing:** Write simple **unit test** (`tests/core/test_logger.py`) to verify logger initialization and basic message logging. *(Completed)*
*   [x] Create full project directory structure.

**Completion:**

*   [ ] All items above checked.
*   [x] Phase 0 deliverables are ready and documented/committed. *(Code/Files part done)*