# src/core/models.py
"""Pydantic models for configuration validation."""

from pydantic import (
    BaseModel,
    Field,
    model_validator,
    field_validator,
    HttpUrl,
    DirectoryPath,
    FilePath,
    validator,
    PositiveInt,
    NonNegativeFloat,
)
from typing import Optional, Literal, Dict, List, Any
import os
from pathlib import Path

# Placeholder for now, will be populated based on config.yml structure


class GeneralSettings(BaseModel):
    app_name: str = "SolanaPumpSniper"
    app_env: Literal["development", "production"]
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    dry_run: bool = True  # Safety default


class DatabaseConfig(BaseModel):
    db_path: DirectoryPath = Field(default="db")
    dev_db_file: str = "devnet_sniper.sqlite"
    prod_db_file: str = "mainnet_sniper.sqlite"
    _full_db_path: Optional[FilePath] = None

    @field_validator("db_path", mode='before')
    @classmethod
    def ensure_db_path_exists(cls, v):
        v_str = str(v)
        if not os.path.exists(v_str):
            os.makedirs(v_str)
        return v


class RpcConfig(BaseModel):
    devnet_http_url: Optional[HttpUrl] = None # Loaded from env
    devnet_wss_url: Optional[str] = None # Loaded from env
    mainnet_http_url: Optional[HttpUrl] = None # Loaded from env
    mainnet_wss_url: Optional[str] = None # Loaded from env
    # Optional: Specific provider URLs if needed for different tiers/features
    helius_devnet_http_url: Optional[HttpUrl] = None
    helius_mainnet_http_url: Optional[HttpUrl] = None
    quicknode_devnet_http_url: Optional[HttpUrl] = None
    quicknode_mainnet_http_url: Optional[HttpUrl] = None

    request_timeout_seconds: PositiveInt = 15
    max_retries: PositiveInt = 3


class ApiKeyConfig(BaseModel):
    # Optional API keys - loader should handle if they are missing
    helius_api_key: Optional[str] = None # Loaded from env
    birdeye_api_key: Optional[str] = None # Loaded from env
    defi_api_key: Optional[str] = None # Loaded from env
    sniperoo_api_key: Optional[str] = None # Loaded from env
    # Note: Jito auth uses a keypair file path, not just a key string


class DetectionSettings(BaseModel):
    enabled: bool = True
    target_dex: Literal["raydium_v4", "pumpswap", "both"] = "raydium_v4"
    # Specific Program IDs (MUST BE VERIFIED)
    # Raydium Liquidity Pool v4
    raydium_v4_devnet_program_id: str = "HWy1jotH36cWeFxYHpgi8hzn7EVGKfom1ueqB9u93dAU" # Example Devnet Raydium LP v4
    raydium_v4_mainnet_program_id: str = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8" # Mainnet Raydium LP v4
    # PumpSwap (Needs Research - Example Placeholder)
    pumpswap_devnet_program_id: Optional[str] = None
    pumpswap_mainnet_program_id: Optional[str] = None
    # Other potential sources/DEXs?

    block_processed_tokens: bool = True # Check DB before processing
    pool_creation_delay_seconds: NonNegativeFloat = 0 # Optional delay after pool detected


# --- Filter Sub-Models ---
class ContractLiquidityFilterSettings(BaseModel):
    enabled: bool = True
    min_initial_sol_liquidity: NonNegativeFloat = 0.1
    max_initial_sol_liquidity: NonNegativeFloat = 10.0
    check_burn_status: bool = False # Requires on-chain check or reliable API
    require_renounced_mint_authority: bool = False
    require_renounced_freeze_authority: bool = False
    check_lp_locks: bool = False # Requires reliable API (e.g., RugCheck, Streamflow)
    min_lp_lock_duration_days: Optional[PositiveInt] = None # If check_lp_locks is True


class MetadataDistributionFilterSettings(BaseModel):
    enabled: bool = True
    check_socials: bool = False # Requires website scraping or API
    require_website: bool = False
    require_twitter: bool = False
    require_telegram: bool = False
    # Holder analysis (usually requires paid API like Helius DAS/Geyser or Birdeye)
    enable_holder_analysis: bool = False
    min_holder_count: Optional[PositiveInt] = 10
    max_creator_holding_pct: Optional[NonNegativeFloat] = 90.0
    max_top_10_holder_pct: Optional[NonNegativeFloat] = 70.0


class RugPullHoneypotFilterSettings(BaseModel):
    enabled: bool = True
    # Basic checks (e.g., if pool exists, tradeable direction)
    check_pool_existence: bool = True
    check_trade_direction: bool = True # Check if SOL -> Token swap is possible
    # External API Checks (Requires API Keys in .env)
    use_external_honeypot_check_api: Literal["none", "goplus", "defi", "both"] = "none"
    fail_if_goplus_error: bool = False # Should bot stop if GoPlus check fails?
    fail_if_defi_error: bool = False # Should bot stop if De.Fi check fails?


# --- Main FilterSettings Model ---
class FilterSettings(BaseModel):
    enabled: bool = True
    contract_liquidity: ContractLiquidityFilterSettings
    metadata_distribution: MetadataDistributionFilterSettings
    rug_pull_honeypot: RugPullHoneypotFilterSettings
    # Add more filter groups here? e.g., Volume/Velocity (needs real-time data)


class SniperooSettings(BaseModel):
    base_url: HttpUrl = "https://api.sniperoo.com" # Example URL
    # API key loaded from ApiKeyConfig/env


class JitoSettings(BaseModel):
    block_engine_url: Optional[str] = None # Loaded from env
    auth_keypair_path: Optional[FilePath] = None # Loaded from env
    tip_lamports: PositiveInt = 10000 # Example tip


class ExecutionSettings(BaseModel):
    enabled: bool = True
    provider: Literal["SELF_BUILT", "SNIPEROO_API", "JITO_BUNDLER"] = "SELF_BUILT"
    buy_amount_sol: NonNegativeFloat = 0.01 # Start very small
    slippage_percent: NonNegativeFloat = 25.0 # High for sniping, adjust based on testing
    # Self-Built Specific
    compute_unit_limit: PositiveInt = 1_400_000 # Max default
    compute_unit_price_micro_lamports: PositiveInt = 10_000 # Adjust based on network
    # Transaction Settings
    max_tx_retries: PositiveInt = 3
    tx_confirmation_timeout_seconds: PositiveInt = 60
    use_transaction_simulation: bool = False # Use simulateTransaction RPC before sending
    # Provider Specific Settings (Keys loaded separately)
    sniperoo: Optional[SniperooSettings] = None
    jito: Optional[JitoSettings] = None


class MonitoringSettings(BaseModel):
    enabled: bool = True
    # Only enable auto-sell if using SELF_BUILT or if provider doesn't handle it
    enable_auto_sell: bool = True
    poll_interval_seconds: PositiveInt = 10
    # Basic TP/SL
    take_profit_pct: Optional[NonNegativeFloat] = 100.0 # e.g., 2x
    stop_loss_pct: Optional[NonNegativeFloat] = 50.0
    # Advanced TP/SL (Future)
    enable_trailing_stop_loss: bool = False
    trailing_stop_loss_trigger_pct: Optional[NonNegativeFloat] = 50.0 # e.g., Activate TSL when price is 50% up
    trailing_stop_loss_delta_pct: Optional[NonNegativeFloat] = 15.0 # e.g., Sell if price drops 15% from peak after trigger
    enable_multi_level_take_profit: bool = False
    take_profit_levels: Optional[List[Dict[str, NonNegativeFloat]]] = None # e.g., [{'pct': 50, 'amount_pct': 50}, {'pct': 100, 'amount_pct': 50}]
    # Time Stop
    enable_time_stop: bool = False
    time_stop_minutes: Optional[PositiveInt] = 60


class AppConfig(BaseModel):
    """Root model representing the entire configuration."""
    general: GeneralSettings
    database: DatabaseConfig
    rpc: RpcConfig
    api_keys: ApiKeyConfig = Field(default_factory=ApiKeyConfig) # Ensure it exists even if empty in YAML
    detection: DetectionSettings
    filtering: FilterSettings
    execution: ExecutionSettings
    monitoring: MonitoringSettings

    # --- Loaded from Environment / Resolved by Loader ---
    dev_wallet_private_key: Optional[str] = None
    prod_wallet_private_key: Optional[str] = None
    jito_auth_keypair_path: Optional[FilePath] = None # For Jito

    # Resolved paths/values to be populated by the loader
    active_db_file_path: Optional[FilePath] = None
    active_http_url: Optional[HttpUrl] = None
    active_wss_url: Optional[str] = None
    active_private_key: Optional[str] = None
    active_raydium_program_id: Optional[str] = None
    active_pumpswap_program_id: Optional[str] = None

    @model_validator(mode='before')
    @classmethod
    def load_env_vars(cls, data: Any) -> Any:
        """Explicitly load known env vars into the dictionaries for validation."""
        if not isinstance(data, dict):
            return data # Skip if not dictionary input

        # Ensure nested dicts exist
        rpc = data.setdefault('rpc', {})
        api_keys = data.setdefault('api_keys', {})

        rpc['devnet_http_url'] = os.getenv("DEVNET_HTTP_URL", rpc.get('devnet_http_url'))
        rpc['devnet_wss_url'] = os.getenv("DEVNET_WSS_URL", rpc.get('devnet_wss_url'))
        rpc['mainnet_http_url'] = os.getenv("MAINNET_HTTP_URL", rpc.get('mainnet_http_url'))
        rpc['mainnet_wss_url'] = os.getenv("MAINNET_WSS_URL", rpc.get('mainnet_wss_url'))
        # Add specific provider URLs if needed
        rpc['helius_devnet_http_url'] = os.getenv("HELIUS_DEVNET_HTTP_URL", rpc.get('helius_devnet_http_url'))
        # ... etc

        api_keys['helius_api_key'] = os.getenv("HELIUS_API_KEY", api_keys.get('helius_api_key'))
        api_keys['birdeye_api_key'] = os.getenv("BIRDEYE_API_KEY", api_keys.get('birdeye_api_key'))
        api_keys['defi_api_key'] = os.getenv("DEFI_API_KEY", api_keys.get('defi_api_key'))
        api_keys['sniperoo_api_key'] = os.getenv("SNIPEROO_API_KEY", api_keys.get('sniperoo_api_key'))

        # No need to assign back, modifying data in place
        return data

    @model_validator(mode='after')
    def check_jito_config(self) -> 'AppConfig': # Use forward reference
        """Load Jito env vars and ensure consistency if Jito provider is selected."""
        # Access fields via self after initial validation
        if self.execution and self.execution.provider == "JITO_BUNDLER":
            jito_auth_path_str = os.getenv("JITO_AUTH_KEYPAIR_PATH")
            jito_block_engine = os.getenv("JITO_BLOCK_ENGINE_URL")
            if not jito_auth_path_str or not jito_block_engine:
                raise ValueError("JITO_AUTH_KEYPAIR_PATH and JITO_BLOCK_ENGINE_URL must be set in environment variables when JITO_BUNDLER provider is selected.")
            if not os.path.exists(jito_auth_path_str):
                raise ValueError(f"Jito auth keypair file not found at path: {jito_auth_path_str}")

            # Set the resolved path on the model instance
            self.jito_auth_keypair_path = Path(jito_auth_path_str)

            # Ensure jito settings exist in execution config and update them
            if not self.execution.jito:
                self.execution.jito = JitoSettings()
            self.execution.jito.block_engine_url = jito_block_engine
            self.execution.jito.auth_keypair_path = Path(jito_auth_path_str)
        return self

    @model_validator(mode='after')
    def check_sniperoo_config(self) -> 'AppConfig':
        """Ensure Sniperoo key is set if provider is selected."""
        # Access fields via self
        if self.execution and self.execution.provider == "SNIPEROO_API":
            if not self.api_keys or not self.api_keys.sniperoo_api_key:
                raise ValueError("SNIPEROO_API_KEY must be set in environment variables when SNIPEROO_API provider is selected.")
            # Ensure sniperoo settings exist
            if not self.execution.sniperoo:
                self.execution.sniperoo = SniperooSettings()
        return self
