from fastapi import APIRouter, WebSocket
import aio_pika

from src.database.DAO.crud import MessageRecordDAO
from src.utils.rmq.consumer import latest_message
from src.utils.rmq.RabbitModel import rmq

rmqSession = MessageRecordDAO

router = APIRouter(prefix="/rmq", tags=["RabbitMQ"])


@router.websocket("/ws/chat/{chat_id}")
async def websocket_endpoint(websocket: WebSocket, chat_id: str):
    await websocket.accept()

    await rmq.conntect()
    channel = rmq.channel()

    exchange = await rmq.declare_exchange("chat_exchange", aio_pika.ExchangeType.DIRECT)

    queue = await channel.declare_queue(exclusive=True, auto_delete=True)
    await queue.bind(exchange, routing_key=chat_id)

    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            async with message.process():
                await websocket.send_text(message.body.decode())

    await rmq.close()

