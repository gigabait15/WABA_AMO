from typing import Any, Optional, Type

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from waba_api.src.database.models.base import Base
from waba_api.src.database.models.MetaModels import Messages
from waba_api.src.settings.engine import async_session_maker


class BaseDAO:
    model: Type[Base]
    _session_factory = async_session_maker

    @classmethod
    async def get_session(cls) -> AsyncSession:
        return cls._session_factory()

    @classmethod
    async def get_all_items(cls):
        async with await cls.get_session() as session:
            result = await session.execute(select(cls.model))
            return result.scalars().all()

    @classmethod
    async def find_item_by_id(cls, item_id: int) -> Optional[Base]:
        async with await cls.get_session() as session:
            result = await session.execute(select(cls.model).filter_by(id=item_id))
            return result.scalar_one_or_none()

    @classmethod
    async def add(cls, **values: Any) -> Base:
        async with await cls.get_session() as session:
            async with session.begin():
                new_instance = cls.model(**values)
                session.add(new_instance)
            return new_instance

    @classmethod
    async def update(cls, item_id: int, **values: Any) -> Optional[Base]:
        async with await cls.get_session() as session:
            async with session.begin():
                item = await cls.find_item_by_id(item_id)
                if item is None:
                    return None
                for key, val in values.items():
                    if hasattr(item, key):
                        setattr(item, key, val)
                session.add(item)

                await session.refresh(item)

            return item


class MessagesDAO(BaseDAO):
    model = Messages

    @classmethod
    async def get_last_items(cls, limit: int = 10):
        """
        Вернёт последние `limit` записей из таблицы, отсортированные по полю date.
        """
        async with await cls.get_session() as session:
            stmt = (
                select(cls.model)
                .order_by(desc(cls.model.date))
                .limit(limit)
            )
            result = await session.execute(stmt)
            return result.scalars().all()

    @classmethod
    async def add_many(cls, values_list: list[dict]) -> list[model]:
        """
        Добавление нескольких оюъектов в базу данных
        :param values_list: список объектов
        :return: список добавленных объектов
        """
        async with await cls.get_session() as session:
            async with session.begin():
                new_items = [cls.model(**v) for v in values_list]
                session.add_all(new_items)
            return new_items