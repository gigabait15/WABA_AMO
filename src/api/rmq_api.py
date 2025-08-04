from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import aio_pika

from src.utils.rmq.RabbitModel import get_rmq_dependency, AsyncRabbitMQRepository

from src.settings.conf import log

router = APIRouter(prefix="/rmq", tags=["RabbitMQ"])


@router.websocket("/ws/chat/{chat_id}")
async def websocket_endpoint(websocket: WebSocket, chat_id: str):
    await websocket.accept()
    rmq = get_rmq_dependency()

    try:
        await rmq.connect()
        channel = rmq.channel

        exchange = await channel.declare_exchange(
            "chat_exchange",
            aio_pika.ExchangeType.DIRECT,
            durable=True,
            auto_delete=False,
        )

        queue = await channel.declare_queue(exclusive=True, auto_delete=True)

        await queue.bind(exchange, routing_key=chat_id)

        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                async with message.process():
                    await websocket.send_text(message.body.decode())

    except WebSocketDisconnect:
        pass
    except Exception as e:
        log.error(f"[WebSocket] Ошибка: {e}")
    finally:
        pass
