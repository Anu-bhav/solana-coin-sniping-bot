import pytest
import os
import yaml
import sys
from pathlib import Path
from pydantic import ValidationError
from src.config.loader import load_configuration
from src.core.models import AppConfig

# Helper to create temp env file
@pytest.fixture
def temp_env_file(tmp_path):
    env_content = '''
# Minimal Dev Env
DEV_WALLET_PRIVATE_KEY=[1,2,3]
DEVNET_HTTP_URL=http://dev.rpc
DEVNET_WSS_URL=ws://dev.rpc

# Optional keys for testing override
HELIUS_API_KEY=env_helius_key
'''
    env_path = tmp_path / ".env.test"
    env_path.write_text(env_content)
    return str(env_path)

# Helper to create temp config file
@pytest.fixture
def temp_config_file(tmp_path):
    config_content = '''
general:
  project_name: Test Sniper Bot
  version: 0.1.0
  environment: development

logging:
  level: INFO
  log_to_file: false
  log_file_path: null

rpc:
  devnet_http: null # Should be loaded from env
  devnet_wss: null # Should be loaded from env
  mainnet_http: null # Placeholder
  mainnet_wss: null # Placeholder

wallet:
  dev_private_key: null # Should be loaded from env
  prod_private_key: null # Placeholder

api_keys:
  helius_api_key: config_helius_key
  birdeye_api_key: null
  defi_api_key: null
  sniperoo_api_key: null

detection:
  enabled: true
  source: HELIUS_WSS
  helius_webhook_id: null

filtering:
  enabled: true
  min_liquidity_usd: 100
  check_mutable_metadata: true
  check_freeze_authority: true
  check_mint_authority: true
  required_dex: RAYDIUM
  # ... other filter defaults

execution:
  enabled: true
  provider: SELF_BUILT # Default to self-built for basic tests
  buy_amount_sol: 0.001
  slippage_percent: 25.0
  compute_unit_limit: 300000
  compute_unit_price_micro_lamports: 5000
  sniperoo:
    base_url: https://default.sniperoo
  jito:
    tip_lamports: 1000
  max_tx_retries: 1
  tx_confirmation_timeout_seconds: 60
  use_transaction_simulation: false

monitoring:
  enabled: false
  enable_auto_sell: false
  poll_interval_seconds: 30
  # ... other monitoring defaults
'''
    config_path = tmp_path / "config.test.yml"
    config_path.write_text(config_content)
    return str(config_path)

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

def test_load_config_defaults(temp_config_file, temp_env_file):
    """Test loading config with minimal env overrides."""
    # Ensure env vars that might conflict are unset
    if 'LOG_LEVEL' in os.environ: del os.environ['LOG_LEVEL']
    if 'SNIPEROO_API_KEY' in os.environ: del os.environ['SNIPEROO_API_KEY']
    if 'JITO_AUTH_KEYPAIR_PATH' in os.environ: del os.environ['JITO_AUTH_KEYPAIR_PATH']

    # Pass the paths from fixtures to the loader
    config = load_configuration(config_path=temp_config_file, env_path=temp_env_file)

    # Assert the loaded config is the correct type
    assert isinstance(config, AppConfig)

    # Assert default values from YAML are loaded
    assert config.general.project_name == "Test Sniper Bot"
    assert config.logging.level == "INFO"
    assert config.rpc.devnet_http == "http://dev.rpc"
    assert config.rpc.devnet_wss == "ws://dev.rpc"
    assert config.wallet.dev_private_key == [1, 2, 3]
    assert config.api_keys.helius_api_key == "env_helius_key" # Env overrides config
    assert config.execution.provider == "SELF_BUILT"
    assert config.execution.slippage_percent == 25.0

def test_load_config_env_override(temp_config_file, temp_env_file):
    """Test environment variables override config file values."""
    os.environ['LOG_LEVEL'] = 'DEBUG' # Override logging level
    os.environ['SLIPPAGE_PERCENT'] = '50.5' # Override slippage

    # Pass the paths from fixtures to the loader
    config = load_configuration(config_path=temp_config_file, env_path=temp_env_file)

    assert isinstance(config, AppConfig)
    assert config.general.log_level == 'DEBUG' # Check override
    assert config.rpc.devnet_http == "http://dev.rpc" # From .env.test
    assert config.wallet.dev_private_key == "[1,2,3]" # From .env.test
    assert config.api_keys.helius_api_key == "env_helius_key" # From .env.test

def test_missing_required_env_vars(tmp_path, temp_config_file):
    """Test validation fails if required env vars are missing for SELF_BUILT provider."""
    # Create an incomplete env file (missing DEV_WALLET_PRIVATE_KEY)
    env_content = '''
    # Missing DEV_WALLET_PRIVATE_KEY
    DEVNET_HTTP_URL=http://dev.rpc
    DEVNET_WSS_URL=ws://dev.rpc
    '''
    env_path = tmp_path / ".env.incomplete"
    env_path.write_text(env_content)

    # Assuming load_configuration tries to load default .env files
    # Clear relevant env vars if they exist from previous tests/env
    if "DEV_WALLET_PRIVATE_KEY" in os.environ:
        del os.environ["DEV_WALLET_PRIVATE_KEY"]
    if "DEVNET_HTTP_URL" in os.environ:
        del os.environ["DEVNET_HTTP_URL"]
    if "DEVNET_WSS_URL" in os.environ:
        del os.environ["DEVNET_WSS_URL"]

    # Use a config that sets SELF_BUILT provider
    # Create a temp config with SELF_BUILT
    config_content_self_built = """
    execution:
      provider: SELF_BUILT
      buy_amount_sol: 0.01
      slippage_percent: 20
    # ... include other necessary sections from base config ...
    general:
      app_name: TestApp
      log_level: INFO
      dry_run: true
    database:
      db_path: db
      dev_db_file: dev.db
      prod_db_file: prod.db
    rpc:
      request_timeout_seconds: 10
      max_retries: 2
    api_keys: {}
    detection:
      enabled: true
      target_dex: raydium_v4
      raydium_v4_devnet_program_id: test_id
      raydium_v4_mainnet_program_id: test_id
      block_processed_tokens: true
      pool_creation_delay_seconds: 0
    filtering:
      enabled: true
      contract_liquidity:
        enabled: true
        min_initial_sol_liquidity: 0.1
      metadata_distribution:
        enabled: false
      rug_pull_honeypot:
        enabled: true
    sniper_settings:
      auto_sell_delay_seconds: 60
      take_profit_percentage: 100
      stop_loss_percentage: 50
    wallet:
      dev_wallet_name: dev
      prod_wallet_name: prod
    scheduled_tasks:
      clean_old_logs_days: 7
      monitor_sell_task_seconds: 5
      pump_token_monitor_seconds: 1
    rate_limits:
      global_requests_per_second: 10
    performance:
      max_concurrent_tasks: 5
    telegram_bot:
      enabled: false
    advanced:
      enable_tx_simulation: true
      transaction_priority_fee_lamports: 10000
      jito_tip_lamports: 10000
      auto_retry_failed_tx: true
      max_buy_retries: 3
      max_sell_retries: 3
      confirmation_timeout_seconds: 60
      skip_confirmation_for_sell: false
      sell_confirmation_timeout_seconds: 30
      price_impact_protection_percent: 5
      rug_check_timeout_seconds: 10
      initial_buy_delay_ms: 0
      randomize_buy_delay_ms: 0
      min_pool_age_seconds: 0
      max_pool_age_seconds: 300
      min_required_liquidity_sol: 0.5
      max_allowed_liquidity_sol: 100
      min_market_cap_usd: 0
      max_market_cap_usd: 10000
      min_24h_volume_usd: 0
      max_holder_count: 10000
      burn_check_required: false
      min_buy_size_sol: 0.01
      max_buy_size_sol: 1
      slippage_retry_attempts: 2
      slippage_retry_delay_ms: 500
      health_check_interval_seconds: 60
      cache_duration_seconds: 60
      websocket_reconnect_delay_seconds: 5
      max_open_positions: 5
      position_timeout_seconds: 3600
      blacklist_refresh_interval_minutes: 60
      minimum_profit_for_sell_usd: 1
      sell_trigger_cooldown_seconds: 10
      emergency_sell_slippage_percent: 50
      ui_refresh_interval_seconds: 5
      max_log_file_size_mb: 100
      log_backup_count: 5
      dashboard_port: 8080
      enable_auto_update: false
      update_check_interval_hours: 24
      dev_fund_donation_percent: 1
      max_slippage_adjustment_attempts: 3
      max_slippage_percent_limit: 70
      min_time_before_sell_seconds: 5
      sell_strategy: fixed_percent # or trailing_stop
      trailing_stop_percent: 10
      price_check_interval_ms: 500
      order_book_depth: 10
      transaction_simulation_retries: 2
      rpc_failover_threshold: 3
      rpc_failover_delay_seconds: 10
      max_price_staleness_seconds: 15
      api_request_timeout_seconds: 10
      max_token_cache_size: 1000
      db_commit_interval_seconds: 30
      allow_unfunded_pool_snipe: false
      min_pool_size_usd: 100
      auto_adjust_priority_fees: true
      max_priority_fee_lamports: 100000
      min_priority_fee_lamports: 1000
      priority_fee_check_interval_seconds: 30
      anti_rug_min_score: 50
      jito_bundle_size: 3
      bundle_submission_interval_ms: 100
      bundle_timeout_seconds: 10
      sniperoo_max_retries: 3
      sniperoo_retry_delay_ms: 1000
      min_token_age_minutes: 1
      ignore_tokens_with_keywords: ["scam", "rug"]
      liquidity_pool_refresh_interval_seconds: 5
      max_allowed_creator_balance_percent: 75
      time_limit_buy_seconds: 60
      auto_blacklist_failed_buys: true
      consecutive_fail_threshold: 3
      blacklist_duration_minutes: 30
      max_rpc_connections: 10
      rpc_connection_timeout_seconds: 20
      use_rpc_load_balancing: true
      max_analysis_time_ms: 500
      enable_multithreading: true
      num_worker_threads: 4
      min_raydium_pool_size_sol: 0.1
      pump_fun_pool_creation_fee_sol: 0.01
      max_buy_attempts_per_token: 5
      sell_on_liquidity_removal: true
      liquidity_removal_threshold_percent: 50
      min_time_stop_minutes: 10
    monitoring: # Added missing section
      health_check_interval_seconds: 60
      transaction_monitoring_interval_seconds: 5
    """
    self_built_config_path = tmp_path / "self_built_config.yml"
    self_built_config_path.write_text(config_content_self_built)

    with pytest.raises(ValidationError) as excinfo:
        load_configuration(config_path=str(self_built_config_path), env_path=str(env_path))

    assert "DEV_WALLET_PRIVATE_KEY must be set" in str(excinfo.value)

def test_invalid_yaml_format(tmp_path):
    """Test loading with an invalid YAML file."""
    invalid_yaml_content = '''
general:
  app_name: Test
invalid_indentation_or_structure: { key: value
'''
    invalid_yaml_path = tmp_path / "invalid_config.yaml"
    invalid_yaml_path.write_text(invalid_yaml_content)

    with pytest.raises(yaml.YAMLError):
        load_configuration(config_path=str(invalid_yaml_path))

    # Clean up the invalid file
    invalid_yaml_path.unlink()

def test_non_existent_config_file(tmp_path):
    """Test loading with a non-existent config file path."""
    non_existent_path = tmp_path / "not_a_real_config.yaml"
    # load_configuration should handle the missing file and return None
    result = load_configuration(config_path=str(non_existent_path))
    assert result is None
