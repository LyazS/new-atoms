from pathlib import Path
import sys

from loguru import logger

from app.config.settings import settings


def setup_logging() -> None:
    logger.remove()
    logger.add(
        sys.stdout,
        level=settings.log_level.upper(),
        colorize=True,
        backtrace=False,
        diagnose=False,
    )

    if settings.log_file_path:
        log_file = Path(settings.log_file_path)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        logger.add(
            log_file,
            level=settings.log_level.upper(),
            colorize=False,
            backtrace=False,
            diagnose=False,
            rotation=settings.log_file_rotation,
            retention=settings.log_file_retention,
            encoding="utf-8",
        )
