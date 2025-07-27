from pydantic import BaseModel


class IncomingMessage(BaseModel):
    external_user_id: str
    message: str


class OutgoingMessage(BaseModel):
    external_user_id: str
    message: str


class TemplateSchemas(BaseModel):
    name: str
    content: str
    is_editable: bool = False
    type: str = "waba"
    waba_header_type: str = "text"
    external_id: str
    waba_category: str
    waba_language: str
    waba_header: str
    waba_footer: str
