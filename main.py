import os

import uvicorn
from fastapi import FastAPI

from src.api.amo_meta import router as amo_meta_router
from src.api.amoCRM_API import router as amocrm_router
from src.api.meta_api import router as webhook_router

app = FastAPI(
    title="WhatsApp Business Webhook",
    version="1.0.0",
    description="Приём/отправка сообщений WhatsApp Business через Cloud API",
)
app.include_router(router=webhook_router)
app.include_router(router=amocrm_router)
app.include_router(router=amo_meta_router)

@app.get("/")
async def root():
    return {"message": "APP is working"}

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=bool(os.getenv("DEV", False)),
        log_level="info",
    )