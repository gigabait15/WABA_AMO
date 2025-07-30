from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, validator


class TemplateSendRequest(BaseModel):
    to: str = Field(..., description="Телефон получателя в формате E.164")
    template_name: str = Field(..., description="Имя шаблона (name из Meta)")
    language_code: str = Field(..., description="Язык шаблона, например 'en_US'")


class SendRequest(BaseModel):
    """Структура тела запроса на /send."""

    wa_id: str = Field(..., description="Номер телефона получателя")
    text: str = Field(..., description="Текст сообщения")


class TestR(BaseModel):
    wa_id: str = Field(..., description="Номер телефона получателя")
    text: str = Field(..., description="Текст сообщения")
    oper_num: str = Field(..., description="Operator")

    @validator("wa_id")
    def wa_id_must_be_digits(cls, v: str) -> str:
        if not v.isdigit():
            raise ValueError("wa_id должен содержать только цифры")
        return v


class PhoneNumber(BaseModel):
    cc: str = Field(..., description="код страны без '+'")
    phone_number: str = Field(..., description="номер телефона")
    display_name: str = Field(..., description="Отображаемое имя WhatsApp Business")
    verified_name: str = Field(
        ..., description="Проверенное имя компании (из Meta Business)"
    )


class SuccessPhoneNumber(BaseModel):
    phone_number_id: str = Field(..., description="получен при регистрации номера")
    verification_code: str = Field(
        ..., description="отправленный код на номер указанный при регистрации"
    )

class StatusEnum(str, Enum):
    sent = "sent"
    delivered = "delivered"
    read = "read"


class MessageOut(BaseModel):
    id: str
    sender: str
    text: Optional[str]
    media: Optional[str]
    timestamp: datetime
    status: StatusEnum

    class Config:
        orm_mode = True