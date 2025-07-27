from sqlalchemy.engine import Engine, create_engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import sessionmaker

from src.settings.conf import dbsettings


class DBConnection:
    def __init__(self):
        """
        Инициализирует подключение, устанавливая асинхронный SQLAlchemy движок.
        :param: Объект с конфигурацией базы данных.
        """
        self.settings = dbsettings
        self.engine = self.init_async_engine()

    def init_async_engine(self) -> AsyncEngine:
        """
        Создает асинхронный SQLAlchemy движок для подключения к PostgreSQL с использованием asyncpg.
        :return: Экземпляр AsyncEngine.
        """
        link = (
            f"postgresql+asyncpg://{self.settings.DB_USER}:{self.settings.DB_PASSWORD}"
            f"@{self.settings.DB_HOST}:{self.settings.DB_PORT}/{self.settings.DB_NAME}"
        )
        return create_async_engine(link, echo=True)

    def init_engine(self) -> Engine:
        """
        Создает синхронный SQLAlchemy движок для подключения к PostgreSQL.
        :return: Экземпляр Engine.
        """
        link = (
            f"postgresql+psycopg://{self.settings.DB_USER}:{self.settings.DB_PASSWORD}"
            f"@{self.settings.DB_HOST}:{self.settings.DB_PORT}/{self.settings.DB_NAME}"
        )
        return create_engine(link, isolation_level="AUTOCOMMIT", echo=True)

    def async_session_maker(self) -> async_sessionmaker[AsyncSession]:
        """
        Создает фабрику асинхронных сессий для работы с базой данных.
        :return: Объект sessionmaker для асинхронных сессий.
        """
        return sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)


conn = DBConnection()
async_session_maker = conn.async_session_maker()
