from typing import Any, Optional, Type

from sqlalchemy import asc, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.base import Base
from src.database.models.Models import (
    Deals,
    MessageRecord,
    Messages,
    OperatorsData,
    Templates,
)
from src.settings.engine import async_session_maker


class BaseDAO:
    model: Type[Base]
    _session_factory = async_session_maker

    @classmethod
    async def get_session(cls) -> AsyncSession:
        return cls._session_factory()

    @classmethod
    async def get_all_items(
        cls,
        limit: int = 100,
        offset: int = 0,
        filters: dict = None,
        sort_by: str = None,
        sort_desc: bool = False,
    ):
        async with await cls.get_session() as session:
            query = select(cls.model)

            if filters:
                for field, value in filters.items():
                    column = getattr(cls.model, field, None)
                    if column is not None:
                        query = query.where(column == value)

            if sort_by:
                column = getattr(cls.model, sort_by, None)
                if column is not None:
                    query = query.order_by(desc(column) if sort_desc else asc(column))

            query = query.limit(limit).offset(offset)

            result = await session.execute(query)
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
                query = select(cls.model).filter_by(id=values["id"])
                result = await session.execute(query)
                existing = result.scalar_one_or_none()
                if existing:
                    return existing

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
                await session.flush()
                await session.refresh(item)
            return item


class MessagesDAO(BaseDAO):
    model = Messages

    @classmethod
    async def upsert(cls, **values: Any) -> Base:
        item = await cls.find_item_by_id(values["id"])
        if item:
            return await cls.update(values["id"], **values)
        return await cls.add(**values)


class DealsDAO(BaseDAO):
    model = Deals

    @classmethod
    async def add(cls, **values: Any) -> Deals:
        if "conversation_id" not in values:
            raise ValueError("conversation_id is required for DealsDAO.add")

        async with await cls.get_session() as session:
            async with session.begin():
                query = select(cls.model).filter_by(
                    conversation_id=values["conversation_id"]
                )
                result = await session.execute(query)
                existing = result.scalar_one_or_none()
                if existing:
                    return existing

                new_instance = cls.model(**values)
                session.add(new_instance)
            return new_instance

    @classmethod
    async def find_id(cls, client_phone: str, operator_phone: str) -> Optional[Deals]:
        async with await cls.get_session() as session:
            query = select(cls.model).where(
                cls.model.client_phone == client_phone,
                cls.model.operator_phone == operator_phone,
            )
            result = await session.execute(query)
            return result.scalars().first()


class TemplatesDAO(BaseDAO):
    model = Templates


class OperatorsDAO(BaseDAO):
    model = OperatorsData


class MessageRecordDAO(BaseDAO):
    model = MessageRecord

    @classmethod
    async def search(cls):
        async with cls.get_session() as session:
            result = await session.execute(
                cls.model.__table__.select().order_by(cls.model.id.desc())
            )
            messages = result.fetchall()
            return [
                {"id": m.id, "source": m.source, "content": m.content} for m in messages
            ]
