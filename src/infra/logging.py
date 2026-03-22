from __future__ import annotations

import logging


def get_logger(name: str) -> logging.Logger:
    """Simple logger factory scaffold for upcoming structured logging work."""
    return logging.getLogger(name)

