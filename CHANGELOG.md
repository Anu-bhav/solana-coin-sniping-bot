# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2025-04-04
### Added
- **Phase 1: Core Clients & Database**
    - Implemented `DatabaseManager` (`database/database_manager.py`) for SQLite interactions.
    - Added basic unit tests for `DatabaseManager` (`tests/database/test_manager.py`).
    - Implemented `SolanaClient` (`src/clients/solana_client.py`) for interacting with Solana RPC.
    - Added basic unit tests for `SolanaClient` (`tests/clients/test_solana_client.py`).
    - Implemented `HttpClient` (`src/clients/http_client.py`) using `aiohttp` for general HTTP requests.
    - Added basic unit tests for `HttpClient` (`tests/clients/test_http_client.py`).
    - Defined database schema in `database/schema.sql`.

### Changed
- Updated project status to reflect Phase 1 completion and Phase 2 start.

## [0.1.0] - 2025-03-31
### Added
- Initial project structure setup (Phase 0).
- Python virtual environment setup using `uv`.
- Core dependencies installation (`solana`, `pydantic`, `structlog`, `aiohttp`, etc.).
- `.gitignore` file for Python projects.
- `requirements.txt` generated via `uv pip freeze`.
- Basic directory structure (`src`, `tests`, `config`, `db`, `logs`).
- Pydantic models for configuration validation (`src/core/models.py`).
- Configuration loader (`src/config/loader.py`) reading `.env` and `config.yml`.
- Basic structured logging setup using `structlog` (`src/core/logger.py`).
- Unit tests for configuration loading and validation (`tests/config/test_loader.py`).
- Unit tests for logger initialization (`tests/core/test_logger.py`).
- Placeholder `config/config.yml` and `.env.dev` files.
- Initial `README.md` and `CHANGELOG.md` files.

### Changed
- Formatted code using `black`.
- Linted code using `ruff`.
