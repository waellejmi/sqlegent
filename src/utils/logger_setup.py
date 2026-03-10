import logging


class LoggerSetup:
    @staticmethod
    def get_logger(name: str, level: int) -> logging.Logger:
        logger = logging.getLogger(name)
        logger.setLevel(level)
        return logger
