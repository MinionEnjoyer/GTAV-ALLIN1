import logging

from allin1 import logging as app_logging


def test_setup_logging_configures_file_console_and_is_idempotent(tmp_path, monkeypatch):
    logger = logging.getLogger("allin1")
    old_handlers = list(logger.handlers)
    logger.handlers.clear()
    monkeypatch.setattr(app_logging, "_initialized", False)
    try:
        app_logging.setup_logging(tmp_path, verbose=True)
        assert (tmp_path / "allin1.log").exists()
        assert len(logger.handlers) == 2
        assert all(handler.level == logging.DEBUG for handler in logger.handlers)
        app_logging.setup_logging(tmp_path)
        assert len(logger.handlers) == 2
    finally:
        for handler in logger.handlers:
            handler.close()
        logger.handlers[:] = old_handlers


def test_setup_logging_default_root_and_info_console(tmp_path, monkeypatch):
    logger = logging.getLogger("allin1")
    old_handlers = list(logger.handlers)
    logger.handlers.clear()
    monkeypatch.setattr(app_logging, "_initialized", False)
    (tmp_path / "a").mkdir()
    monkeypatch.setattr(app_logging.Path, "resolve", lambda _self: tmp_path / "a/b/c.py")
    try:
        app_logging.setup_logging(verbose=False)
        assert any(handler.level == logging.INFO for handler in logger.handlers)
    finally:
        for handler in logger.handlers:
            handler.close()
        logger.handlers[:] = old_handlers
