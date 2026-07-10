"""Structured logging configuration."""

import logging

from app.config import get_settings

_configured = False


def configure_logging() -> None:
    global _configured
    if _configured:
        return
    logging.basicConfig(
        level=get_settings().log_level,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    )
    _configured = True


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)
