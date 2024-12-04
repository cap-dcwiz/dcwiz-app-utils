import logging
import os
from logging.handlers import TimedRotatingFileHandler


def initialize_logger(
    level=logging.INFO, fmt="%(asctime)s | %(levelname)8s | %(message)s"
):
    """
    Initializes a logger with the specified format and level
    :param level: level of the logger
    :param fmt: format of the log messages
    :return: logger object
    """

    if isinstance(level, str):
        level = getattr(logging, level.upper())

    logger = logging.getLogger()
    logger.setLevel(level)

    stdout_handler = logging.StreamHandler()
    stdout_handler.setLevel(level)
    stdout_handler.setFormatter(CustomFormatter(fmt))

    log_handler = CustomRotatingFileHandler(
        filename="log/app.log",
        when="midnight",  # Rotate at midnight
        interval=1,  # Rotate every 1 day
        backupCount=7,  # Keep the last 7 days of logs
        encoding="utf-8",
    )
    log_handler.setLevel(level)
    log_handler.setFormatter(CustomFormatter(fmt))
    logger.addHandler(log_handler)
    logger.addHandler(stdout_handler)

    uvicorn_logger = logging.getLogger("uvicorn")
    uvicorn_logger.addHandler(log_handler)
    uvicorn_logger.addHandler(stdout_handler)
    uvicorn_logger.propagate = False

    access_logger = logging.getLogger("uvicorn.access")
    access_logger.addHandler(log_handler)
    access_logger.addHandler(stdout_handler)
    access_logger.propagate = False

    return logger


class CustomRotatingFileHandler(TimedRotatingFileHandler):
    def __init__(
        self,
        filename,
        when="h",
        interval=1,
        backupCount=0,
        encoding=None,
        delay=False,
        utc=False,
        atTime=None,
        errors=None,
    ):
        directory = os.path.dirname(filename)
        if directory:
            os.makedirs(directory, exist_ok=True)
        super().__init__(
            filename, when, interval, backupCount, encoding, delay, utc, atTime, errors
        )


class CustomFormatter(logging.Formatter):
    """Logging colored formatter, adapted from https://stackoverflow.com/a/56944256/3638629"""

    grey = "\x1b[38;21m"
    blue = "\x1b[38;5;39m"
    yellow = "\x1b[38;5;226m"
    red = "\x1b[38;5;196m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"

    def __init__(self, fmt):
        super().__init__()
        self.fmt = fmt
        self.FORMATS = {
            logging.DEBUG: self.grey + self.fmt + self.reset,
            logging.INFO: self.blue + self.fmt + self.reset,
            logging.WARNING: self.yellow + self.fmt + self.reset,
            logging.ERROR: self.red + self.fmt + self.reset,
            logging.CRITICAL: self.bold_red + self.fmt + self.reset,
        }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)
