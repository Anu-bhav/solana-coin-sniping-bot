import logging
import os
import structlog
import sys
from pathlib import Path

# Add project root to sys.path to find 'src'
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from src.core.logger import configure_logging, get_logger

def test_configure_logging_defaults():
    """Test that configure_logging sets up structlog correctly with defaults."""
    # configure_logging sets up the global structlog config, get_logger gets an instance
    configure_logging() # Call with defaults
    logger = get_logger("test_default_logger")

    # Check that structlog has been configured
    assert structlog.is_configured()

    # Check that the underlying standard library logger has the default level (INFO)
    root_logger = logging.getLogger() # Get the root logger
    # If using specific loggers, ensure their level propagates or check root
    assert root_logger.level == logging.INFO

def test_configure_logging_debug_level_override():
    """Test that configure_logging sets DEBUG level via override argument."""
    configure_logging(log_level_override='DEBUG')
    logger = get_logger("test_debug_logger")
    root_logger = logging.getLogger()
    assert root_logger.level == logging.DEBUG

# Add more tests later if needed (e.g., checking file output if logging to file)
# Or testing with a mock AppConfig object
