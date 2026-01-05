"""Loguru logging configuration for jaacountable-backend.

This module provides centralized logging configuration using Loguru.
Call configure_logging() at application startup to initialize logging.
"""
import os
import sys
import logging
from loguru import logger


def configure_logging(
    log_level: str | None = None,
    enable_json: bool = False,
    enable_file_logging: bool = False,
    log_file_path: str = "logs/jaacountable.log",
) -> None:
    """
    Configure Loguru logging for the application.

    This function:
    1. Removes default Loguru handler
    2. Adds custom console handler with formatting
    3. Optionally adds JSON and file handlers
    4. Intercepts standard library logging for third-party compatibility
    5. Sets log level from environment variable or parameter

    Args:
        log_level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
                   Defaults to LOG_LEVEL env var or INFO.
        enable_json: Enable JSON structured logging format
        enable_file_logging: Enable file logging in addition to console
        log_file_path: Path for log file (default: logs/jaacountable.log)

    Example:
        # In main.py or application entry point
        from config.log_config import configure_logging

        configure_logging()  # Uses defaults
        configure_logging(log_level="DEBUG", enable_file_logging=True)
    """
    # Determine log level (priority: parameter > env var > default)
    if log_level is None:
        log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    # Validate log level
    valid_levels = ["TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"]
    if log_level not in valid_levels:
        log_level = "INFO"

    # Remove default handler (Loguru adds stderr handler by default)
    logger.remove()

    # Console handler with custom format
    if enable_json:
        # JSON format for production/structured logging
        logger.add(
            sys.stderr,
            level=log_level,
            serialize=True,  # JSON output
        )
    else:
        # Human-readable format for development
        log_format = (
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        )
        logger.add(
            sys.stderr,
            format=log_format,
            level=log_level,
            colorize=True,
        )

    # Optional file handler with rotation
    if enable_file_logging:
        logger.add(
            log_file_path,
            rotation="100 MB",  # Rotate when file reaches 100 MB
            retention="30 days",  # Keep logs for 30 days
            compression="zip",  # Compress rotated logs
            level=log_level,
            serialize=enable_json,  # Use JSON format if enabled
        )

    # Intercept standard library logging for third-party compatibility
    # This captures logs from httpx, asyncpg, feedparser, etc.

    class InterceptHandler(logging.Handler):
        """
        Intercept standard library logging and redirect to Loguru.

        This ensures third-party libraries using standard logging
        (httpx, asyncpg, feedparser, etc.) are captured by Loguru.
        """
        def emit(self, record: logging.LogRecord) -> None:
            # Get corresponding Loguru level if it exists
            try:
                level = logger.level(record.levelname).name
            except ValueError:
                level = record.levelno

            # Find caller from where the logged message originated
            frame, depth = logging.currentframe(), 2
            while frame and frame.f_code.co_filename == logging.__file__:
                frame = frame.f_back
                depth += 1

            logger.opt(depth=depth, exception=record.exc_info).log(
                level, record.getMessage()
            )

    # Set up interception for all existing loggers
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

    # Suppress overly verbose third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("asyncpg").setLevel(logging.WARNING)
    logging.getLogger("feedparser").setLevel(logging.WARNING)

    logger.info(f"Logging configured: level={log_level}, json={enable_json}, file={enable_file_logging}")


# Export logger for convenience
__all__ = ["logger", "configure_logging"]
