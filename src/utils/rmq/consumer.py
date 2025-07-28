import traceback

import httpx

from src.database.DAO.crud import MessageRecordDAO
from src.settings.conf import log
from waba_api.src.utils.rmq.RabbitModel import rmq

session = MessageRecordDAO()


latest_message = {"data": None}


async def consume_messages():
    async def handle_message(msg: str):
        try:
            source, content = msg.split(":", 1)
            latest_message["data"] = {"source": source, "content": content}

            await session.add(source=source, content=content)

            async with httpx.AsyncClient() as client:
                await client.post(
                    "http://localhost:8000/rmq/webhook", json=latest_message["data"]
                )
        except Exception:
            log.error(traceback.format_exc())

    await rmq.consume_messages("webhook_messages", handle_message)
