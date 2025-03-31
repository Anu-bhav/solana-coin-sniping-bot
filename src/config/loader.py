# src/config/loader.py
"""Loads and validates configuration from .env and config.yml."""

import os
import yaml
from dotenv import load_dotenv
from pydantic import ValidationError
from typing import Optional
import logging

# Assuming models are defined in src.core.models
# Adjust import path if your structure differs
from src.core.models import AppConfig

# Use standard logging temporarily until structlog is configured
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def load_configuration(
    config_path: str = "config/config.yml",
    env_path: Optional[str] = None,
) -> Optional[AppConfig]:
    """
    Loads configuration from environment variables and YAML file,
    validates it using Pydantic models, and populates active settings.

    Args:
        config_path (str): Path to the YAML configuration file.
        env_path (Optional[str]): Path to the environment file. If None, uses default logic.

    Returns:
        Optional[AppConfig]: The validated configuration object or None if loading/validation fails.
    """
    try:
        # 1. Determine Environment (default to development)
        app_env = os.getenv("APP_ENV", "development").lower()
        logger.info(f"Loading configuration for environment: {app_env}")

        # 2. Load .env file
        if env_path:
            # Use provided env_path directly
            if not os.path.exists(env_path):
                logger.warning(f"Provided environment file '{env_path}' not found. Relying on system env vars.")
                load_dotenv()
            else:
                load_dotenv(dotenv_path=env_path)
                logger.info(f"Loaded environment variables from: {env_path}")
        else:
            # Default behavior: find .env based on APP_ENV
            env_file = f".env.{app_env}"
            if not os.path.exists(env_file):
                logger.warning(
                    f"Environment file '{env_file}' not found. Relying on system env vars."
                )
                load_dotenv()  # Load system env vars if file doesn't exist
            else:
                load_dotenv(dotenv_path=env_file)
                logger.info(f"Loaded environment variables from: {env_file}")

        # 3. Load config.yml
        if not os.path.exists(config_path):
            logger.error(f"Configuration file '{config_path}' not found.")
            return None

        with open(config_path, "r") as f:
            try:
                config_yaml = yaml.safe_load(f)
                if not config_yaml:
                    logger.error(
                        f"Configuration file '{config_path}' is empty or invalid yaml."
                    )
                    return None
                logger.info(f"Loaded base configuration from: {config_path}")
            except yaml.YAMLError as e:
                logger.error(f"Error parsing YAML file '{config_path}': {e}", exc_info=True)
                raise

        # 4. Prepare data for Pydantic model (merge env vars conceptually)
        # Pydantic model will automatically look for matching env vars if field is not in yaml
        # We specifically load keys here for clarity and potential overrides

        config_data = config_yaml.copy()

        # Manually load potentially sensitive or env-specific keys
        # Ensure general.app_env is set correctly
        if "general" not in config_data:
            config_data["general"] = {}
        config_data["general"]["app_env"] = app_env

        # Load RPC URLs from env vars if defined there
        if "rpc" not in config_data:
            config_data["rpc"] = {}
        config_data["rpc"]["devnet_http_url"] = os.getenv(
            "DEVNET_HTTP_URL", config_data.get("rpc", {}).get("devnet_http_url")
        )
        config_data["rpc"]["devnet_wss_url"] = os.getenv(
            "DEVNET_WSS_URL", config_data.get("rpc", {}).get("devnet_wss_url")
        )
        config_data["rpc"]["mainnet_http_url"] = os.getenv(
            "MAINNET_HTTP_URL", config_data.get("rpc", {}).get("mainnet_http_url")
        )
        config_data["rpc"]["mainnet_wss_url"] = os.getenv(
            "MAINNET_WSS_URL", config_data.get("rpc", {}).get("mainnet_wss_url")
        )

        # Load API Keys from env vars
        if "api_keys" not in config_data:
            config_data["api_keys"] = {}
        config_data["api_keys"]["helius_api_key"] = os.getenv(
            "HELIUS_API_KEY", config_data.get("api_keys", {}).get("helius_api_key")
        )
        config_data["api_keys"]["dexscreener_api_key"] = os.getenv(
            "DEXSCREENER_API_KEY",
            config_data.get("api_keys", {}).get("dexscreener_api_key"),
        )
        config_data["api_keys"]["birdeye_api_key"] = os.getenv(
            "BIRDEYE_API_KEY", config_data.get("api_keys", {}).get("birdeye_api_key")
        )
        # ... load other API keys ...

        # Load Wallet Private Keys (separate from main config dict for Pydantic)
        dev_wallet_pk = os.getenv("DEV_WALLET_PRIVATE_KEY")
        prod_wallet_pk = os.getenv("PROD_WALLET_PRIVATE_KEY")

        # DEBUG: Print the dictionary before passing to Pydantic
        print(f"DEBUG: config_data before Pydantic validation: {config_data}")

        # 5. Validate using Pydantic
        try:
            validated_config = AppConfig(**config_data)
            # Assign loaded private keys after validation
            validated_config.dev_wallet_private_key = dev_wallet_pk
            validated_config.prod_wallet_private_key = prod_wallet_pk
            logger.info("Configuration successfully validated.")
        except ValidationError as e:
            logger.error(f"Configuration validation failed:\n{e}")
            return None

        # 6. Populate Active Settings based on Environment
        db_config = validated_config.database
        rpc_config = validated_config.rpc

        if app_env == "production":
            validated_config.active_db_file_path = os.path.join(
                db_config.db_path, db_config.prod_db_file
            )
            validated_config.active_http_url = rpc_config.mainnet_http_url
            validated_config.active_wss_url = rpc_config.mainnet_wss_url
            validated_config.active_private_key = (
                validated_config.prod_wallet_private_key
            )
            if not validated_config.active_private_key:
                logger.warning("PROD_WALLET_PRIVATE_KEY is not set in .env.production!")
        else:  # Default to development
            validated_config.active_db_file_path = os.path.join(
                db_config.db_path, db_config.dev_db_file
            )
            validated_config.active_http_url = rpc_config.devnet_http_url
            validated_config.active_wss_url = rpc_config.devnet_wss_url
            validated_config.active_private_key = (
                validated_config.dev_wallet_private_key
            )
            if not validated_config.active_private_key:
                logger.warning("DEV_WALLET_PRIVATE_KEY is not set in .env.dev!")

        # Ensure active paths/URLs are set before returning
        if not validated_config.active_http_url or not validated_config.active_wss_url:
            logger.error(
                f"Active HTTP or WSS URL could not be determined for env '{app_env}'. Check config.yml and {env_file}."
            )
            return None

        # Populate the internal _full_db_path in the DatabaseConfig model
        # This assumes the validator ran and created the db_path directory
        if validated_config.active_db_file_path:
            validated_config.database._full_db_path = (
                validated_config.active_db_file_path
            )

        logger.info(f"Active DB path: {validated_config.active_db_file_path}")
        logger.info(f"Active HTTP URL: {validated_config.active_http_url}")
        logger.info(f"Active WSS URL: {validated_config.active_wss_url}")

        return validated_config

    except (yaml.YAMLError, ValidationError):
        raise
    except Exception as e:
        logger.error(
            f"An unexpected error occurred during configuration loading: {e}", exc_info=True
        )
        return None


# Example usage (for testing purposes)
if __name__ == "__main__":
    print("Attempting to load configuration...")
    config = load_configuration()
    if config:
        print("\nConfiguration loaded successfully!")
        # print(config.model_dump_json(indent=2))
        print(f"\nAPP_ENV: {config.general.app_env}")
        print(f"Dry Run: {config.general.dry_run}")
        print(f"Active DB File: {config.active_db_file_path}")
        print(f"Active HTTP RPC: {config.active_http_url}")
        print(f"Active WSS RPC: {config.active_wss_url}")
        print(f"Active Private Key Set: {bool(config.active_private_key)}")
        print(f"Helius Key Set: {bool(config.api_keys.helius_api_key)}")
    else:
        print("\nConfiguration loading failed.")
