# src/core/logger.py
"""Configures structured logging using structlog."""

import logging
import sys
import os
import structlog
from structlog.types import Processor
from typing import Optional, Dict, Any

# Assuming the AppConfig model is available
# from .models import AppConfig # Use relative import if called from within src
from src.core.models import AppConfig  # Use this if running scripts directly from root

# --- Structlog Processors ---


def add_log_level_as_string(
    logger: Any, method_name: str, event_dict: Dict[str, Any]
) -> Dict[str, Any]:
    """Adds the log level string (e.g., 'info', 'error') to the event dict."""
    if method_name == "warn":
        method_name = "warning"  # Match standard level names
    event_dict["level"] = method_name
    return event_dict


def add_process_info(
    logger: Any, method_name: str, event_dict: Dict[str, Any]
) -> Dict[str, Any]:
    """Adds process ID and name to the event dict."""
    event_dict["process_id"] = os.getpid()
    # event_dict["process_name"] = threading.current_thread().name # If using threads
    return event_dict


def configure_logging(
    config: Optional[AppConfig] = None, log_level_override: Optional[str] = None
):
    """
    Configures structlog based on the provided configuration or defaults.

    Args:
        config (Optional[AppConfig]): Validated application configuration object.
        log_level_override (Optional[str]): Manually override the log level.
    """
    log_level = "INFO"  # Default log level
    log_to_file = False
    log_file_path = "logs/app.log"

    if config:
        log_level = config.general.log_level
        # Potentially add file logging config to AppConfig.general later
        # log_to_file = config.general.log_to_file
        # log_file_path = config.general.log_file_path

    if log_level_override:
        log_level = log_level_override

    numeric_log_level = getattr(logging, log_level.upper(), logging.INFO)

    # Ensure log directory exists if logging to file
    if log_to_file:
        log_dir = os.path.dirname(log_file_path)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)

    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        add_log_level_as_string,
        add_process_info,
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    # Configure structlog
    structlog.configure(
        processors=shared_processors
        + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure the underlying standard logging formatter
    formatter = structlog.stdlib.ProcessorFormatter(
        # These processors run ONLY on entries processed by standard logging handlers
        processor=structlog.processors.JSONRenderer(),
        # foreign_pre_chain=shared_processors, # Include shared processors for logs from other libs
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    # Set up root logger
    root_logger = logging.getLogger()
    # Remove existing handlers to avoid duplicates if re-configuring
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    root_logger.addHandler(handler)
    root_logger.setLevel(numeric_log_level)

    # Optionally add file handler
    if log_to_file:
        file_handler = logging.FileHandler(log_file_path)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # Configure logging levels for noisy libraries if needed
    # logging.getLogger("websockets").setLevel(logging.WARNING)
    # logging.getLogger("aiohttp").setLevel(logging.WARNING)

    print(
        f"Logging configured. Level: {log_level}"
    )  # Use print as logger might not be fully ready


def get_logger(name: Optional[str] = None) -> Any:
    """Gets a structlog logger instance."""
    return structlog.get_logger(name)


# --- Example Usage ---
if __name__ == "__main__":
    # Example: Configure logging without full config object initially
    print("Configuring default logging...")
    configure_logging(log_level_override="DEBUG")
    log = get_logger("test_logger")

    log.debug("This is a debug message", data=123)
    log.info("This is an info message", user="test")
    log.warning("This is a warning")
    log.error("This is an error", details={"code": 500})
    log.critical("This is critical!")

    # Example with context
    structlog.contextvars.bind_contextvars(request_id="req-123")
    log.info("Message within context")

    try:
        x = 1 / 0
    except ZeroDivisionError:
        log.exception("An exception occurred")

    print("\nExample logging complete. Check console output for JSON logs.")
