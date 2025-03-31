# src/core/models.py
"""Pydantic models for configuration validation."""

from pydantic import (
    BaseModel,
    Field,
    HttpUrl,
    DirectoryPath,
    FilePath,
    validator,
    PositiveInt,
    NonNegativeFloat,
)
from typing import Optional, Literal
import os

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

    @validator("db_path", pre=True, always=True)
    def ensure_db_path_exists(cls, v):
        if not os.path.exists(v):
            os.makedirs(v)
        return v


class RpcConfig(BaseModel):
    devnet_http_url: HttpUrl
    devnet_wss_url: str  # Pydantic HttpUrl doesn't handle wss:// well
    mainnet_http_url: HttpUrl
    mainnet_wss_url: str
    # Add fields for specific provider URLs if needed, e.g., helius_devnet_http
    request_timeout_seconds: PositiveInt = 10
    max_retries: PositiveInt = 3


class ApiKeyConfig(BaseModel):
    # Optional API keys - loader should handle if they are missing
    helius_api_key: Optional[str] = None
    dexscreener_api_key: Optional[str] = None
    birdeye_api_key: Optional[str] = None
    # Add other potential API keys (GoPlus, Sniperoo etc.)


class DetectionSettings(BaseModel):
    enabled: bool = True
    target_dex: Literal["raydium_v4", "pumpswap", "both"] = "raydium_v4"
    # Add specific program IDs later after research
    raydium_v4_program_id: Optional[str] = (
        "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"  # Example MAINNET ID - MUST BE VERIFIED FOR DEVNET
    )
    pumpswap_program_id: Optional[str] = None  # Needs research
    block_processed_tokens: bool = True  # Check DB before processing


class ContractLiquidityFilterSettings(BaseModel):
    enabled: bool = True
    min_initial_sol_liquidity: NonNegativeFloat = 0.1
    max_initial_sol_liquidity: NonNegativeFloat = 10.0
    check_burn_status: bool = False  # Requires more advanced checks
    require_renounced_mint_authority: bool = False
    require_renounced_freeze_authority: bool = False


class MetadataDistributionFilterSettings(BaseModel):
    enabled: bool = True
    check_socials: bool = False  # Requires API integration
    min_holder_count: Optional[PositiveInt] = None  # Requires paid API usually
    max_creator_holding_pct: Optional[NonNegativeFloat] = 90.0  # Requires API


class RugPullHoneypotFilterSettings(BaseModel):
    enabled: bool = True
    # Basic checks possible, advanced need paid tools
    use_external_honeypot_check_api: Literal["none", "goplus", "defi"] = "none"


class FilterSettings(BaseModel):
    enabled: bool = True
    contract_liquidity: ContractLiquidityFilterSettings
    metadata_distribution: MetadataDistributionFilterSettings
    rug_pull_honeypot: RugPullHoneypotFilterSettings
    # Add other filter groups as defined in the master plan


class ExecutionSettings(BaseModel):
    enabled: bool = True
    provider: Literal["SELF_BUILT", "SNIPEROO_API", "JITO_BUNDLER"] = "SELF_BUILT"
    buy_amount_sol: NonNegativeFloat = 0.01  # Start very small
    slippage_percent: NonNegativeFloat = (
        25.0  # High for sniping, adjust based on testing
    )
    compute_unit_limit: PositiveInt = 1_400_000  # Max default
    compute_unit_price_micro_lamports: PositiveInt = 10_000  # Adjust based on network
    max_tx_retries: PositiveInt = 3
    tx_confirmation_timeout_seconds: PositiveInt = 60
    # Sniperoo specific settings
    sniperoo_api_key_env_var: Optional[str] = "SNIPEROO_API_KEY"
    sniperoo_base_url: Optional[HttpUrl] = None


class MonitoringSettings(BaseModel):
    enabled: bool = True
    # Only enable auto-sell if using SELF_BUILT or if provider doesn't handle it
    enable_auto_sell: bool = True
    poll_interval_seconds: PositiveInt = 10
    take_profit_pct: Optional[NonNegativeFloat] = 100.0  # e.g., 2x
    stop_loss_pct: Optional[NonNegativeFloat] = 50.0
    enable_time_stop: bool = False
    time_stop_minutes: Optional[PositiveInt] = 60


class AppConfig(BaseModel):
    """Root model representing the entire configuration."""

    general: GeneralSettings
    database: DatabaseConfig
    rpc: RpcConfig
    api_keys: ApiKeyConfig
    detection: DetectionSettings
    filtering: FilterSettings  # More detailed model needed here eventually
    execution: ExecutionSettings
    monitoring: MonitoringSettings

    # Wallet keys loaded separately from .env
    dev_wallet_private_key: Optional[str] = None
    prod_wallet_private_key: Optional[str] = None

    # Resolved paths/values to be populated by the loader
    active_db_file_path: Optional[FilePath] = None
    active_http_url: Optional[HttpUrl] = None
    active_wss_url: Optional[str] = None
    active_private_key: Optional[str] = None
