#!/usr/bin/env python3
"""
Тестовый скрипт для проверки работы логгера.
"""

from src.settings.logger_config import get_logger
from src.settings.conf import log as main_log

# Создаем логгер для тестирования
log = get_logger(__name__)

def test_logging():
    """Тестовая функция для проверки логирования."""
    log.debug("Это debug сообщение из функции test_logging")
    log.info("Это info сообщение из функции test_logging") 
    log.warning("Это warning сообщение из функции test_logging")
    log.error("Это error сообщение из функции test_logging")

def another_test_function():
    """Еще одна тестовая функция."""
    log.info("Сообщение из another_test_function на строке 18")

def test_main_logger():
    """Тестирование основного логгера."""
    main_log.info("Тест основного логгера из conf.py")

if __name__ == "__main__":
    print("Тестирование логгера...")
    test_logging()
    another_test_function()
    test_main_logger()
    print("Тест завершен. Проверьте файлы логов в папке logs/")
