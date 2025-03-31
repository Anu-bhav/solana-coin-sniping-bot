import logging
import os
import structlog
from core.logger import configure_logging, get_logger

def test_configure_logging_defaults():
    """Test that configure_logging sets up structlog correctly with defaults."""
    # configure_logging sets up the global structlog config, get_logger gets an instance
    configure_logging() # Call with defaults
    logger = get_logger("test_default_logger")

    # Check that the logger is a structlog BoundLogger
    assert isinstance(logger, structlog.stdlib.BoundLogger)

    # Check that the underlying standard library logger has the default level (INFO)
    std_lib_logger = logging.getLogger("test_default_logger")
    assert std_lib_logger.level == logging.INFO

def test_configure_logging_debug_level_override():
    """Test that configure_logging sets DEBUG level via override argument."""
    configure_logging(log_level_override='DEBUG')
    logger = get_logger("test_debug_logger")
    std_lib_logger = logging.getLogger("test_debug_logger")
    assert std_lib_logger.level == logging.DEBUG

# Add more tests later if needed (e.g., checking file output if logging to file)
# Or testing with a mock AppConfig object
