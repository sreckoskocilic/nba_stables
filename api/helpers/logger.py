import logging
import os
from logging.handlers import RotatingFileHandler

ERROR_LOG_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "../../logs/error.log"
)
os.makedirs(os.path.dirname(ERROR_LOG_FILE), exist_ok=True)

logger = logging.getLogger(__name__)
rotating_logfile_handler = RotatingFileHandler(
    ERROR_LOG_FILE,
    maxBytes=2 * 1024 * 1024,
    backupCount=5,
    encoding="utf-8",
)

formatter = logging.Formatter("%(asctime)s [%(levelname)s] - %(message)s")
rotating_logfile_handler.setFormatter(formatter)

logger.addHandler(rotating_logfile_handler)


def log_exceptions(exception: Exception, context: str | None = None):
    if context:
        logger.exception("%s | context=%s", exception, context)
    else:
        logger.exception(exception)
