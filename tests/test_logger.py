"""Log output tests isolated from the production log and other loggers."""

import logging
import re
from uuid import uuid4

import pytest

from app.utils.logger import setup_logger


@pytest.fixture
def logger_name():
    name = f"test.pipeline.{uuid4().hex}"
    yield name
    logger = logging.getLogger(name)
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()


def test_info_logging_creates_parent_and_formats_message(tmp_path, logger_name):
    path = tmp_path / "logs" / "pipeline.log"
    logger = setup_logger(path, name=logger_name)
    logger.debug("debug should be filtered")
    logger.info("Pipeline started — بدء التشغيل")
    content = path.read_text(encoding="utf-8")
    assert logger.level == logging.INFO
    assert re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}.* \| INFO \|", content)
    assert "Pipeline started — بدء التشغيل" in content
    assert "debug should be filtered" not in content


def test_repeated_initialization_writes_once(tmp_path, logger_name):
    path = tmp_path / "pipeline.log"
    first = setup_logger(str(path), name=logger_name)
    handler = first.handlers[0]
    second = setup_logger(path, name=logger_name)
    assert first is second
    assert second.handlers == [handler]
    assert second.propagate is False
    second.info("once only")
    assert path.read_text(encoding="utf-8").count("once only") == 1


def test_changing_destination_closes_old_file_handler(tmp_path, logger_name):
    old_path = tmp_path / "old.log"
    new_path = tmp_path / "new.log"
    logger = setup_logger(old_path, name=logger_name)
    old_handler = logger.handlers[0]
    logger.info("old destination")
    setup_logger(new_path, name=logger_name).info("new destination")
    assert len(logger.handlers) == 1
    assert old_handler.stream is None
    assert "new destination" not in old_path.read_text(encoding="utf-8")
    assert "new destination" in new_path.read_text(encoding="utf-8")


@pytest.mark.parametrize("path,error", [(None, TypeError), (42, TypeError), ("", ValueError), (" ", ValueError)])
def test_invalid_log_path(path, error, logger_name):
    with pytest.raises(error):
        setup_logger(path, name=logger_name)


def test_directory_log_path(tmp_path, logger_name):
    with pytest.raises(IsADirectoryError, match="Log path is a directory"):
        setup_logger(tmp_path, name=logger_name)
