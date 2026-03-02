"""Structured JSON logging configuration.

Configures the root logger to output JSON-formatted log lines to both
stdout and a file (``./logs``) using python-json-logger. Each line
includes asctime, levelname, and message.
"""

import logging
import os
import sys

from pythonjsonlogger import jsonlogger

from app.config import get_settings


def setup_logging() -> None:
    """Configure the root logger for structured JSON output.

    Reads LOG_LEVEL from application settings and sets up two handlers:
    1. A StreamHandler writing to stdout.
    2. A FileHandler writing to ``./logs`` in the project root.

    Both handlers use a JsonFormatter that includes asctime, levelname,
    and message fields on every log line.
    """
    settings = get_settings()

    formatter = jsonlogger.JsonFormatter(
        fmt="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)

    log_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs")
    file_handler = logging.FileHandler(log_path, mode="a", encoding="utf-8")
    file_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(stdout_handler)
    root_logger.addHandler(file_handler)
    root_logger.setLevel(settings.LOG_LEVEL.upper())
