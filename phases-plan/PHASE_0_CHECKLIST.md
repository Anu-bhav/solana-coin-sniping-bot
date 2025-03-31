# Phase 0 Checklist: Strategic Foundation & Prerequisite Setup

**Goal:** Ensure all foundational elements are researched, set up, configured, and validated before core bot development begins.

**General:**

*   [ ] Confirm understanding of Phase 0 Goals and Deliverables.
*   [ ] Document Scope & Constraints formally (in README or design doc).
*   [ ] Document initial Devnet Success Criteria.

**Research:**

*   [ ] Document findings on Solana fundamentals (Accounts, TXs, Fees, etc.).
*   [ ] Document findings on Pump.fun mechanics (Graduation, Contract Patterns).
*   [ ] **Identify and Document precise Devnet Program IDs** for target DEX(s) (Raydium LP v4 / PumpSwap AMM).
*   [ ] **Analyze and Document structure** of target DEX `Initialize` and `Swap` instructions on Devnet.
*   [ ] Compile list of common Solana scam vectors and potential detection ideas.

**Environment & Dependencies:**

*   [ ] Install correct Python version (3.9+).
*   [ ] Create and activate Python virtual environment (`venv`).
*   [ ] Initialize Git repository.
*   [ ] Create comprehensive `.gitignore` file (including `.env*`, `__pycache__/`, `logs/`, `db/*.sqlite`).
*   [ ] Install all dependencies listed in Tech Stack via `pip`.
*   [ ] Generate and commit `requirements.txt` or `pyproject.toml`.
*   [ ] Install and configure Linter (`ruff`) and Formatter (`black`). Run initial format/lint check.

**Infrastructure & Configuration:**

*   [ ] Generate **new dedicated Devnet Solana wallet**.
*   [ ] Securely store Devnet private key in `.env.dev`.
*   [ ] Fund Devnet wallet with sufficient SOL from a faucet. Verify balance.
*   [ ] Sign up for Free Tiers: QuickNode.
*   [ ] Sign up for Free Tiers: Helius.
*   [ ] Sign up for Free Tiers: DexScreener (if key offered).
*   [ ] Sign up for Free Tiers: Birdeye (if key offered).
*   [ ] Populate `.env.dev` with Devnet RPC URLs and any obtained API keys.
*   [ ] Create `config/config.yml` with the detailed structure from the plan. Populate with sensible Devnet defaults. Commit `config.yml`.
*   [ ] Implement `src/config/loader.py`.
    *   [ ] Define comprehensive `pydantic` models for the entire config structure.
    *   [ ] Implement loading of `.env` based on `APP_ENV`.
    *   [ ] Implement loading of `config.yml`.
    *   [ ] Implement merging/handling of secrets from `.env`.
    *   [ ] Implement **rigorous validation** using `pydantic` models.
    *   [ ] **Testing:** Write **unit tests** (`tests/unit/config/test_loader.py`) for `loader.py`:
        *   [ ] Test successful loading with valid Devnet config/env.
        *   [ ] Test successful loading with valid Prod config/env (using dummy prod env).
        *   [ ] Test failure on missing `config.yml`.
        *   [ ] Test failure on invalid YAML format.
        *   [ ] Test failure on missing required fields in config (pydantic validation).
        *   [ ] Test failure on incorrect data types in config (pydantic validation).
        *   [ ] Test failure on missing required environment variables (`.env`).
        *   [ ] Test correct selection of network settings based on `APP_ENV`.
*   [ ] Implement `src/core/logger.py` using `structlog`.
    *   [ ] Configure based on loaded config (level, file, format).
    *   [ ] **Testing:** Write simple **unit test** (`tests/unit/core/test_logger.py`) to verify logger initialization and basic message logging.
*   [ ] Create full project directory structure.

**Completion:**

*   [ ] All items above checked.
*   [ ] Phase 0 deliverables are ready and documented/committed.