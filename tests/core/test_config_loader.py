import pytest
import os
import yaml
import sys
from pathlib import Path
from pydantic import ValidationError
from src.core.config_loader import load_config
from src.core.models import Config

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

    config = load_config(config_path=temp_config_file, env_path=temp_env_file)

    assert isinstance(config, Config)
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

    config = load_config(config_path=temp_config_file, env_path=temp_env_file)

    assert config.logging.level == "DEBUG"
    assert config.execution.slippage_percent == 50.5

    # Clean up
    del os.environ['LOG_LEVEL']
    del os.environ['SLIPPAGE_PERCENT']

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

    # Use the temp_config_file fixture which has SELF_BUILT provider
    with pytest.raises(ValidationError) as excinfo:
        load_config(config_path=temp_config_file, env_path=str(env_path))

    # Check if the error message relates to the missing key (specific check depends on Pydantic version)
    assert "DEV_WALLET_PRIVATE_KEY" in str(excinfo.value).upper()
    # Or check for a specific validation context if model provides it
    assert "VALUE ERROR, DEV_WALLET_PRIVATE_KEY IS REQUIRED FOR SELF_BUILT EXECUTION" in str(excinfo.value).upper()

def test_missing_sniperoo_key(temp_config_file, temp_env_file):
    """Test validation fails if SNIPEROO_API_KEY is missing when provider is SNIPEROO_API."""
    # Modify config content in memory before loading
    with open(temp_config_file, 'r') as f:
        config_dict = yaml.safe_load(f)
    config_dict['execution']['provider'] = 'SNIPEROO_API'

    temp_sniperoo_config_path = os.path.join(os.path.dirname(temp_config_file), "config.sniperoo.test.yml")
    with open(temp_sniperoo_config_path, 'w') as f:
        yaml.dump(config_dict, f)

    # Ensure the key is not in the environment
    if 'SNIPEROO_API_KEY' in os.environ: del os.environ['SNIPEROO_API_KEY']

    with pytest.raises(ValidationError) as excinfo:
        load_config(config_path=temp_sniperoo_config_path, env_path=temp_env_file)

    assert "SNIPEROO_API_KEY" in str(excinfo.value).upper()
    # assert "Value error, SNIPEROO_API_KEY is required for SNIPEROO_API execution" in str(excinfo.value)


# Add more tests for Jito key path validation, other overrides, edge cases etc.
