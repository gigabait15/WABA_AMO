from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, declared_attr


class Base(AsyncAttrs, DeclarativeBase):
    """
    Абстрактный базовый класс для всех ORM-моделей SQLAlchemy.
    Наследуется от AsyncAttrs и DeclarativeBase, что позволяет использовать асинхронную работу с SQLAlchemy
    и декларативное определение моделей.
    """
    __abstract__ = True

    @declared_attr.directive
    def __tablename__(cls) -> str:
        """
        Автоматически генерирует имя таблицы, используя имя класса.
        :return: Имя таблицы как строка.
        """
        return f"{cls.__name__.lower()}"