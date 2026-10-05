"""Reusable INFO-level file logging for the pipeline."""

import logging
from pathlib import Path


def setup_logger(log_path: str | Path, name: str = "pipeline") -> logging.Logger:
    """Configure a named logger with one UTF-8 file handler and no propagation.

    Pass config['logging']['path'] from load_config for the production log.
    Repeated calls reuse the handler; changing the destination replaces and
    closes previous file handlers on this logger. Non-file handlers are retained.
    Relative paths supplied directly are relative to the working directory.
    """
    if not isinstance(log_path, (str, Path)):
        raise TypeError("log_path must be a string or pathlib.Path")
    if isinstance(log_path, str) and not log_path.strip():
        raise ValueError("log_path must not be empty")
    path = Path(log_path).resolve()
    if path.is_dir():
        raise IsADirectoryError(f"Log path is a directory: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)
    file_handlers = [
        handler for handler in logger.handlers
        if isinstance(handler, logging.FileHandler)
    ]
    handler = next(
        (item for item in file_handlers if Path(item.baseFilename) == path), None
    )
    if handler is None:
        handler = logging.FileHandler(path, encoding="utf-8")
        logger.addHandler(handler)
    for previous in file_handlers:
        if previous is not handler:
            logger.removeHandler(previous)
            previous.close()
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger
