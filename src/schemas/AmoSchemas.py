from pydantic import BaseModel


class IncomingMessage(BaseModel):
    external_user_id: str
    message: str

class OutgoingMessage(BaseModel):
    external_user_id: str
    message: str
