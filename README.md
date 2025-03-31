# Solana Pump.fun Sniper Bot (Project PumpSniper)

A configurable Python bot designed to automatically detect, filter, and trade new SPL tokens launched on Pump.fun shortly after they gain liquidity on Raydium or PumpSwap.

**⚠️ WARNING: Trading memecoins and using automated bots is extremely high risk. This is an educational project and not financial advice. You could lose all your funds. USE AT YOUR OWN RISK, preferably only on Devnet for learning purposes. ⚠️**

## Current Status

- **Phase:** Phase 0: Strategic Foundation & Prerequisite Setup (Complete)
- **Next Phase:** Phase 1: Core Service Implementation (Detection & DB)

## Overview

This project aims to build an automated trading bot with the following key capabilities:

1.  **Detection:** Monitor the Solana blockchain (via RPC/WSS) for new liquidity pools created for tokens originating from Pump.fun on specified DEXs (Raydium v4, PumpSwap).
2.  **Filtering:** Apply a configurable multi-stage filtering pipeline to detected tokens to mitigate risks (e.g., check liquidity, mint/freeze authority, holder distribution, potential honeypot checks).
3.  **Execution:** Execute buy orders for filtered tokens using specified parameters (buy amount, slippage, priority fees) via self-built transaction logic or external execution providers (e.g., Sniperoo API, Jito Bundler - future).
4.  **Position Management:** Monitor active positions and automatically execute sell orders based on configurable take-profit, stop-loss, or time-limit conditions.
5.  **State Tracking:** Persist all operational data (detected tokens, executed trades, errors) in a local SQLite database.
6.  **Configuration:** Allow extensive customization via a `config.yml` file and environment variables (`.env` files for secrets).
7.  **Safety:** Prioritize Devnet testing, simulation (`dry_run` mode), and cautious Mainnet deployment.

## Project Structure

```
.                           # Project Root
├── .env.dev                # Devnet secrets (Wallet PK, RPC URLs, API Keys) - DO NOT COMMIT
├── .env.prod               # Mainnet secrets (future) - DO NOT COMMIT
├── .gitignore              # Git ignore rules
├── CHANGELOG.md            # Log of project changes
├── README.md               # This file
├── config/
│   └── config.yml          # Non-secret configuration parameters
├── db/                     # SQLite database files (ignored by git)
│   └── devnet_sniper.sqlite
├── logs/                   # Log files (ignored by git)
│   └── app.log
├── phases-plan/            # Planning documents
│   ├── master-plan.md
│   ├── PHASE_0_CHECKLIST.md
│   ├── PHASE_0_FOUNDATION_SETUP.md
│   └── ... (other phase plans/checklists)
├── requirements.txt        # Pinned Python dependencies
├── src/                    # Source code
│   ├── __init__.py
│   ├── clients/            # Clients for external APIs (RPC, DexScreener, etc.)
│   ├── config/             # Configuration loading logic
│   │   └── loader.py
│   ├── core/               # Core models, logger, utilities
│   │   ├── logger.py
│   │   └── models.py
│   ├── database/           # Database interaction logic (models, queries)
│   ├── providers/          # Execution providers (self-built, APIs)
│   ├── services/           # Core bot services (Detection, Filtering, Execution, Monitoring)
│   └── main.py             # Main application entry point (future)
├── tests/                  # Unit and integration tests
│   ├── __init__.py
│   ├── integration/
│   └── unit/
└── .venv/                  # Python virtual environment (ignored by git)
```

## Getting Started (Development)

1.  **Prerequisites:**
    *   Python 3.9+
    *   `uv` (pipx install uv)
    *   Git

2.  **Clone the repository:**
    ```bash
    git clone https://github.com/Anu-bhav/solana-coin-sniping-bot
    cd solana-coin-sniping-bot
    ```

3.  **Create virtual environment and install dependencies:**
    ```bash
    uv venv
    uv pip install -r requirements.txt
    ```
    *Activate the environment:* `source .venv/bin/activate` (Linux/macOS) or `.venv\Scripts\activate` (Windows PowerShell)

4.  **Set up Configuration:**
    *   **Copy/Rename `.env.example` to `.env.dev` (if example exists) or create `.env.dev` manually.**
    *   **Generate a new Solana wallet FOR DEVNET ONLY.** Use a secure method (e.g., `solana-keygen new --outfile ~/.config/solana/devnet.json`).
    *   **Fund the Devnet wallet** using a faucet (e.g., `solana airdrop 2 <YOUR_DEVNET_WALLET_ADDRESS> --url https://api.devnet.solana.com` or use [https://solfaucet.com/](https://solfaucet.com/)).
    *   **Sign up for RPC services** (e.g., Helius, QuickNode) and get Devnet HTTP/WSS URLs.
    *   **Sign up for optional API services** (DexScreener, Birdeye) if desired.
    *   **Edit `.env.dev`** and add your `DEV_WALLET_PRIVATE_KEY` (paste the private key string), `DEVNET_HTTP_URL`, `DEVNET_WSS_URL`, and any optional API keys.
    *   **Review and customize `config/config.yml`** for Devnet settings (buy amount, slippage, filters, etc.). **KEEP `dry_run: true` INITIALLY.**

5.  **Run Linters/Formatters:**
    ```bash
    black .
    ruff check . --fix
    ```

6.  **(Future) Run Tests:**
    ```bash
    pytest
    ```

7.  **(Future) Run the Bot (Devnet):**
    ```bash
    export APP_ENV=development # Linux/macOS
    # $env:APP_ENV="development" # Windows PowerShell
    python src/main.py
    ```

## Development Workflow

*   Follow the phases outlined in the `phases-plan/` directory.
*   Create feature branches for significant changes.
*   Write unit tests for new logic (`tests/unit/`).
*   Write integration tests where necessary (`tests/integration/`).
*   Ensure code is formatted (`black .`) and linted (`ruff check . --fix`) before committing.
*   Update `CHANGELOG.md` for notable changes.
*   Keep `README.md` updated.

## Disclaimer

This software is provided "as is", without warranty of any kind, express or implied. The authors or copyright holders shall not be liable for any claim, damages or other liability, whether in an action of contract, tort or otherwise, arising from, out of or in connection with the software or the use or other dealings in the software. **Use with extreme caution and understand the risks involved.**
