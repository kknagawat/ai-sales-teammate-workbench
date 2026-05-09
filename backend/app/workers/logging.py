import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from time import gmtime

WORKER_LOG_FILE = Path(__file__).resolve().parents[2] / "logs" / "worker.log"


def configure_worker_file_logging() -> Path:
    WORKER_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    worker_logger = logging.getLogger("app.workers")
    existing = [
        handler
        for handler in worker_logger.handlers
        if isinstance(handler, RotatingFileHandler)
        and Path(handler.baseFilename) == WORKER_LOG_FILE
    ]
    if existing:
        return WORKER_LOG_FILE

    handler = RotatingFileHandler(
        WORKER_LOG_FILE,
        maxBytes=5_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )
    formatter.converter = gmtime
    handler.setFormatter(formatter)
    worker_logger.addHandler(handler)
    worker_logger.setLevel(logging.INFO)
    worker_logger.propagate = False
    return WORKER_LOG_FILE
