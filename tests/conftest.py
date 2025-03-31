import pytest
import os
import tempfile
import shutil

@pytest.fixture(scope="function")
def temp_config_file(tmp_path_factory):
    """Creates a temporary, minimal but valid config file for testing."""
    # Define minimal valid YAML content
    # Include sections that were previously missing based on validation errors
    config_content = """
general:
  app_name: TestSniper
  log_level: INFO
  dry_run: true

database:
  db_path: test_db
  dev_db_file: test_dev.sqlite
  prod_db_file: test_prod.sqlite

rpc:
  request_timeout_seconds: 10
  max_retries: 3

api_keys: {} # Loader expects this to exist

detection:
  enabled: true
  target_dex: raydium_v4
  raydium_v4_devnet_program_id: test_dev_id
  raydium_v4_mainnet_program_id: test_main_id
  block_processed_tokens: true
  pool_creation_delay_seconds: 0

filtering:
  enabled: true
  contract_liquidity:
    enabled: true
    min_initial_sol_liquidity: 0.01
    max_initial_sol_liquidity: 5.0
    check_burn_status: false
    require_renounced_mint_authority: false
    require_renounced_freeze_authority: false
    check_lp_locks: false
    min_lp_lock_duration_days: 30
  metadata_distribution:
    enabled: false
    check_socials: false
    require_website: false
    require_twitter: false
    require_telegram: false
    enable_holder_analysis: false
    min_holder_count: 5
    max_creator_holding_pct: 95.0
    max_top_10_holder_pct: 80.0
  rug_pull_honeypot:
    enabled: true
    check_pool_existence: true
    check_trade_direction: true
    use_external_honeypot_check_api: none
    fail_if_goplus_error: false
    fail_if_defi_error: false

execution:
  enabled: true
  provider: SELF_BUILT # Default to SELF_BUILT for tests unless overridden
  buy_amount_sol: 0.001
  slippage_percent: 25.0
  compute_unit_limit: 1000000
  compute_unit_price_micro_lamports: 5000

sniper_settings:
  auto_sell_delay_seconds: 30
  take_profit_percentage: 50
  stop_loss_percentage: 25

wallet:
  dev_wallet_name: test_dev_wallet
  prod_wallet_name: test_prod_wallet
  # Private keys loaded from env

monitoring: # Added missing section
  health_check_interval_seconds: 60
  transaction_monitoring_interval_seconds: 5

scheduled_tasks:
  clean_old_logs_days: 3
  monitor_sell_task_seconds: 10
  pump_token_monitor_seconds: 2

rate_limits:
  global_requests_per_second: 5

performance:
  max_concurrent_tasks: 3

telegram_bot:
  enabled: false

advanced: # Add a minimal advanced section if needed by model
  enable_tx_simulation: true
  transaction_priority_fee_lamports: 5000
  # Add other minimal required fields from AppConfig.AdvancedConfig if necessary
"""
    # Use tmp_path_factory for better session-scoped temp dirs if needed,
    # but function-scoped tmp_path from pytest is usually fine.
    # Using tmp_path provided by pytest fixture implicitly.
    temp_dir = tmp_path_factory.mktemp("config_test_defaults")
    config_path = temp_dir / "config.test.yml"
    config_path.write_text(config_content)
    print(f"\nCreated temp config: {config_path}") # Debug print
    yield str(config_path)
    # Cleanup handled by pytest tmp_path fixtures

@pytest.fixture(scope="function")
def temp_env_file(tmp_path_factory):
    """Creates a temporary .env file for testing."""
    env_content = """
# Basic .env for testing
APP_ENV=development
DEVNET_HTTP_URL=http://dev.rpc
DEVNET_WSS_URL=ws://dev.rpc
MAINNET_HTTP_URL=http://main.rpc
MAINNET_WSS_URL=ws://main.rpc
DEV_WALLET_PRIVATE_KEY="[1,2,3]" # Example key, ensure it fits expected format
PROD_WALLET_PRIVATE_KEY="[4,5,6]"
HELIUS_API_KEY=env_helius_key
# Add other keys if needed by tests, e.g., SNIPEROO_API_KEY
# SNIPEROO_API_KEY=test_sniperoo_key
"""
    temp_dir = tmp_path_factory.mktemp("env_test")
    env_path = temp_dir / ".env.test"
    env_path.write_text(env_content)
    print(f"\nCreated temp env: {env_path}") # Debug print
    yield str(env_path)
    # Cleanup handled by pytest tmp_path fixtures

# You might need a fixture to set APP_ENV for the duration of tests
# if load_configuration relies on it to find the default .env file
@pytest.fixture(autouse=True)
def set_test_env(monkeypatch):
    """Set APP_ENV to development for tests if needed."""
    monkeypatch.setenv("APP_ENV", "development") # Or parameterize if needed
    # Ensure conflicting real env vars are cleared if they could interfere
    # Example:
    # if "SNIPEROO_API_KEY" in os.environ:
    #     monkeypatch.delenv("SNIPEROO_API_KEY", raising=False)

