from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    UUID,
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.models.base import Base


class StatusEnum(PyEnum):
    sent = "sent"
    delivered = "delivered"
    read = "read"


class Messages(Base):
    id: Mapped[str] = mapped_column(String, primary_key=True)
    sender: Mapped[str] = mapped_column(String, nullable=False, index=True)
    text: Mapped[str] = mapped_column(Text, nullable=True)
    media: Mapped[Text] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[StatusEnum] = mapped_column(
        Enum(StatusEnum), nullable=False, default=StatusEnum.sent
    )

    template_id: Mapped[int] = mapped_column(ForeignKey("templates.id"), nullable=True)
    deals_id: Mapped[int] = mapped_column(ForeignKey("deals.id"), nullable=False)
    deal = relationship("Deals", back_populates="messages")


class Deals(Base):
    id: Mapped[UUID] = mapped_column(UUID, primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String, index=True)
    client_phone: Mapped[str] = mapped_column(String, nullable=False)
    operator_phone: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    messages = relationship("Messages", back_populates="deal")

    __table_args__ = (
        UniqueConstraint("client_phone", "operator_phone", name="uq_client_operator"),
    )


class Templates(Base):
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    language: Mapped[str] = mapped_column(String, nullable=False)


class OperatorsData(Base):
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    account_id: Mapped[int] = mapped_column(BigInteger, index=True)
    number_id: Mapped[int] = mapped_column(BigInteger, index=True)
    number: Mapped[str] = mapped_column(String, nullable=False)


class MessageRecord(Base):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(Text)
