import logging
import subprocess

from sqlalchemy import text
from sqlalchemy.engine import create_engine

from src.settings.conf import dbsettings


def create_database() -> logging:
    """
    Проверяет наличие базы данных и при необходимости создает её.
    Используется синхронное подключение для выполнения CREATE DATABASE, поскольку эта операция
    не поддерживается в асинхронных движках.
    :return: Объект logging, содержащий информацию о результате создания базы данных.
    """
    # Проверяем, запущен ли PostgreSQL
    try:
        subprocess.run(['pg_isready'], check=True)
    except subprocess.CalledProcessError:
        logging.error("PostgreSQL is not running")
        return

    # Создаем базу данных, если она не существует
    engine = create_engine(f"postgresql://{dbsettings.DB_USER}:{dbsettings.DB_PASSWORD}"
                           f"@{dbsettings.DB_HOST}:{dbsettings.DB_PORT}/postgres", isolation_level='AUTOCOMMIT')
    db_name = dbsettings.DB_NAME
    with engine.connect() as connection:
        try:
            result = connection.execute(text(f"SELECT 1 FROM pg_database WHERE datname='{db_name}'"))
            exists = result.scalar() is not None
            if not exists:
                connection.execute(text(f"CREATE DATABASE {db_name}"))
                logging.info(f"Database {db_name} created")
            else:
                logging.info(f"Database {db_name} already exists.")
        except Exception as e:
            logging.error(f"Error while creating database: {e}")
        finally:
            connection.close()

if __name__ == '__main__':
    create_database()