"""Structured logging configuration for IVD monitor."""

import logging
import sys
from pathlib import Path
from typing import Optional


DEFAULT_LOG_DIR = Path("logs")
DEFAULT_LOG_FILE = "ivd_monitor.log"
DEFAULT_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(
    log_file: Optional[Path] = None,
    log_dir: Optional[Path] = None,
    level: int = logging.INFO,
    console: bool = True,
    format_string: Optional[str] = None,
) -> None:
    """Configure structured logging for the IVD monitor.
    
    Args:
        log_file: Path to log file (default: logs/ivd_monitor.log)
        log_dir: Directory for log files (default: logs/)
        level: Logging level (default: INFO)
        console: Whether to also log to console (default: True)
        format_string: Custom log format string
    """
    if log_dir is None:
        log_dir = DEFAULT_LOG_DIR
    
    if log_file is None:
        log_file = log_dir / DEFAULT_LOG_FILE
    elif not log_file.is_absolute():
        log_file = log_dir / log_file
    
    # Ensure log directory exists
    log_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Configure format
    fmt = format_string or DEFAULT_FORMAT
    formatter = logging.Formatter(fmt, datefmt=DEFAULT_DATE_FORMAT)
    
    # Get root logger for ivd_monitor
    logger = logging.getLogger("ivd_monitor")
    logger.setLevel(level)
    
    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()
    
    # File handler
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # Console handler
    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    # Prevent propagation to root logger
    logger.propagate = False
    
    logger.info(f"Logging initialized: {log_file}")


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for a specific module.
    
    Args:
        name: Logger name (typically module name)
        
    Returns:
        Logger instance under the ivd_monitor namespace
    """
    return logging.getLogger(f"ivd_monitor.{name}")
