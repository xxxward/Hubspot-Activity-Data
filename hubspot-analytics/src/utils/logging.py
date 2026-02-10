"""Centralized logging configuration."""

import logging
import sys


def setup_logging(level: int = logging.INFO) -> None:
    """Configure root logger with a clean format."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
        force=True,
    )
    # Quiet noisy libraries
    for name in ("googleapiclient", "google.auth", "urllib3", "gspread"):
        logging.getLogger(name).setLevel(logging.WARNING)
