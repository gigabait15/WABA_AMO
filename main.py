import asyncio
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from src.api.amoCRM_API import router as amocrm_router
from src.api.meta_api import router as webhook_router
from src.api.rmq_api import router as rmq_router
from src.settings.conf import log
from src.utils.redis_conn import redis_client
from src.utils.rmq.RabbitModel import rmq, callback_wrapper


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    log.info("🔌 Connecting to Redis...")
    await rmq.connect()
    await rmq.create_queue("webhook_messages")

    asyncio.create_task(rmq.consume_messages("queue_name", callback_wrapper))
    yield
    # shutdown
    log.info("🛑 Closing Redis connection...")
    await redis_client.close()
    await rmq.close()


app = FastAPI(
    title="WhatsApp Business Webhook",
    version="1.0.0",
    description="Приём/отправка сообщений WhatsApp Business через Cloud API",
    lifespan=lifespan,
)


@app.get("/")
async def root():
    return {"message": "APP is working"}


app.include_router(router=webhook_router)
app.include_router(router=amocrm_router)
app.include_router(router=rmq_router)


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=bool(os.getenv("DEV", False)),
        log_level="info",
    )
