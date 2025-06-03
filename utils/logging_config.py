# utils/logging_config.py
"""
Centralized Logging Configuration

This module sets up a comprehensive logging system for the Discord Academic Jarvis bot.
It provides both console and file logging with configurable levels and automatic log rotation.

Features:
- Console logging with configurable level (default: INFO)
- Optional file logging with daily rotation and 7-day retention
- Consistent formatting across all log messages
- Automatic silencing of noisy third-party libraries
- Environment variable configuration for easy deployment

Environment Variables:
- JARVIS_FILE_LOGS: Set to "true" to enable file logging (default: false)
- JARVIS_CONSOLE_LEVEL: Console log level - DEBUG, INFO, WARNING, ERROR (default: INFO)

Usage:
    from utils.logging_config import logger
    logger.info("This is an info message")
    logger.error("This is an error message")
"""

import logging, sys, os
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

# Configuration from environment variables
LOG_TO_FILE = os.getenv("JARVIS_FILE_LOGS", "false").lower() == "true"
CONSOLE_LVL = os.getenv("JARVIS_CONSOLE_LEVEL", "INFO").upper()

# Consistent log formatting across all handlers
FMT = "[%(asctime)s] %(levelname)-8s | %(name)s:%(lineno)d — %(message)s"
DATEFMT = "%Y-%m-%d %H:%M:%S"
formatter = logging.Formatter(FMT, DATEFMT)

# Create the main logger for the application
root = logging.getLogger("jarvis")
root.setLevel(logging.DEBUG)  # Capture all log levels, handlers will filter

# Configure handlers only once to avoid duplicates
if not root.handlers:
    # Console handler for real-time monitoring
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    console.setLevel(CONSOLE_LVL)
    root.addHandler(console)

    # Optional rotating file handler for persistent logging
    if LOG_TO_FILE:
        # Ensure logs directory exists
        Path("logs").mkdir(exist_ok=True)
        
        # Configure daily log rotation with 7-day retention
        file_hdl = TimedRotatingFileHandler(
            "logs/jarvis.log",
            when="midnight",      # Rotate at midnight each day
            backupCount=7,        # Keep 7 days of log files
            encoding="utf-8",     # Handle unicode characters
            delay=True,           # Don't create file until first log message
        )
        file_hdl.setFormatter(formatter)
        file_hdl.setLevel(logging.DEBUG)  # File logs capture everything
        root.addHandler(file_hdl)

# Reduce noise from third-party libraries
# These libraries tend to be very verbose at DEBUG/INFO levels
logging.getLogger("google").setLevel(logging.WARNING)    # Google API clients
logging.getLogger("httpx").setLevel(logging.WARNING)     # HTTP request library

# Export the configured logger for use throughout the application
logger = root