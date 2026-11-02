"""Log sistemi: teknik ayrıntılar dosyaya yazılır, kullanıcıya gösterilmez."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from app.utils.paths import log_dir

_CONFIGURED = False


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    global _CONFIGURED
    logger = logging.getLogger("mit")
    if _CONFIGURED:
        return logger
    logger.setLevel(level)
    try:
        handler = RotatingFileHandler(
            log_dir() / "app.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
        )
        logger.addHandler(handler)
    except OSError:
        logger.addHandler(logging.NullHandler())
    _CONFIGURED = True
    logger.info("Uygulama başlatıldı")
    return logger


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"mit.{name}")
