import logging
import logging.handlers
from pathlib import Path


def setup_logging_directory():
    """Создает директорию для логов если её нет."""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    return log_dir


def create_formatter() -> logging.Formatter:
    """Создает форматтер с функцией и номером строки."""
    return logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(module)s - %(funcName)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )


def create_file_handler(formatter: logging.Formatter) -> logging.Handler:
    """Создает обработчик для записи в файл с ротацией."""
    file_handler = logging.handlers.RotatingFileHandler(
        "logs/api_log.log",
        maxBytes=10485760,  # 10MB
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    return file_handler


def create_error_handler(formatter: logging.Formatter) -> logging.Handler:
    """Создает обработчик для записи только ошибок."""
    error_handler = logging.handlers.RotatingFileHandler(
        "logs/error.log",
        maxBytes=10485760,  # 10MB
        backupCount=5,
        encoding="utf-8"
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    return error_handler


def create_console_handler(formatter: logging.Formatter) -> logging.Handler:
    """Создает обработчик для консоли."""
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    return console_handler


def setup_main_logger(logger_name: str = "uvicorn.error") -> logging.Logger:
    """
    Настраивает основной логгер приложения.
    
    Args:
        logger_name: Имя логгера
    
    Returns:
        Настроенный логгер
    """
    # Создаем директорию для логов
    setup_logging_directory()
    
    # Настраиваем основной логгер
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.DEBUG)

    # Удаляем существующие обработчики, если они есть
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # Создаем форматтер
    formatter = create_formatter()

    # Создаем и добавляем обработчики
    file_handler = create_file_handler(formatter)
    error_handler = create_error_handler(formatter)
    console_handler = create_console_handler(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(error_handler)
    logger.addHandler(console_handler)

    # Предотвращаем дублирование логов
    logger.propagate = False

    # Отключаем избыточные логи от других библиотек
    logging.getLogger('uvicorn.access').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    
    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Создает и настраивает логгер с правильными обработчиками и форматированием.
    
    Args:
        name: Имя логгера (обычно __name__ модуля)
    
    Returns:
        Настроенный логгер
    """
    logger = logging.getLogger(name)
    
    # Если логгер уже настроен, возвращаем его
    if logger.handlers:
        return logger
    
    logger.setLevel(logging.DEBUG)
    
    # Создаем форматтер с функцией и номером строки
    formatter = create_formatter()
    
    # Обработчик для записи в файл
    file_handler = create_file_handler(formatter)
    
    # Обработчик для консоли
    console_handler = create_console_handler(formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    logger.propagate = False
    
    return logger
