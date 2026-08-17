"""Logging configuration for GTA V ALLIN1.

Sets up dual logging: console output (INFO) and a persistent log file (DEBUG).
The log file is written to the project root as ``allin1.log``.
"""

from __future__ import annotations

import logging
from pathlib import Path

LOG_FILE_NAME = "allin1.log"
_initialized = False


def setup_logging(project_root: Path | None = None, verbose: bool = False) -> None:
    """Configure the ``allin1`` logger hierarchy.

    Parameters
    ----------
    project_root:
        Directory where ``allin1.log`` is written. Defaults to
        the project root (three levels up from this file).
    verbose:
        When True the console handler also uses DEBUG level.
    """
    global _initialized
    if _initialized:
        return
    _initialized = True

    if project_root is None:
        project_root = Path(__file__).resolve().parent.parent.parent

    logger = logging.getLogger("allin1")
    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)-5s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler — captures everything (DEBUG+)
    log_path = project_root / LOG_FILE_NAME
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # Console handler — INFO by default, DEBUG if verbose
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG if verbose else logging.INFO)
    ch.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    logger.addHandler(ch)
