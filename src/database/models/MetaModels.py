from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.database.models.base import Base


class Messages(Base):

    id: Mapped[int]  = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_number: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    operator_number: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    from_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=True)
    media: Mapped[Text] = mapped_column(Text, nullable=True)
    date: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    def to_dict(self):
        return {c.key: getattr(self, c.key) for c in self.__table__.columns}

class LeadBinding(Base):

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_number: Mapped[int] = mapped_column(BigInteger, index=True)
    operator_number: Mapped[int] = mapped_column(BigInteger, index=True)
    lead_id: Mapped[int] = mapped_column(BigInteger, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)