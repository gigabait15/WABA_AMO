from pydantic import BaseModel, Field, validator

class TemplateSendRequest(BaseModel):
    to: str = Field(..., description="Телефон получателя в формате E.164")
    template_name: str = Field(..., description="Имя шаблона (name из Meta)")
    language_code: str = Field(..., description="Язык шаблона, например 'en_US'")

class SendRequest(BaseModel):
    """Структура тела запроса на /send."""

    wa_id: str
    text: str

    @validator("wa_id")
    def wa_id_must_be_digits(cls, v: str) -> str:
        if not v.isdigit():
            raise ValueError("wa_id должен содержать только цифры")
        return v