import logging
import os
from src.core.logger import setup_logging

def test_setup_logging_returns_logger():
    """Test that setup_logging returns a configured logger instance."""
    logger = setup_logging()
    assert isinstance(logger, logging.Logger)
    assert logger.name == "solana_sniper_bot"
    assert logger.level == logging.INFO # Default level

    # Check if file handler was added (optional, depends on implementation)
    # For now, just check type and name is sufficient for basic test

def test_setup_logging_debug_level():
    """Test that setup_logging sets DEBUG level via environment variable."""
    os.environ['LOG_LEVEL'] = 'DEBUG'
    logger = setup_logging()
    assert logger.level == logging.DEBUG
    del os.environ['LOG_LEVEL'] # Clean up environment variable

# Add more tests later if needed (e.g., checking file output if logging to file)
