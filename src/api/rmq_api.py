from fastapi import APIRouter, Request

from src.database.DAO.crud import MessageRecordDAO
from src.utils.rmq.consumer import latest_message
from src.utils.rmq.RabbitModel import rmq

rmqSession = MessageRecordDAO

router = APIRouter(prefix="/rmq", tags=["RabbitMQ"])


@router.get("/webhook")
async def get_latest():
    return latest_message


@router.get("/messages")
async def get_all_messages():
    await rmqSession.search()


@router.post("/send")
async def send_message(request: Request):
    body = await request.json()
    await rmq.send_message("webhook_messages", f"manual:{body}")
    return {"status": "sent"}
