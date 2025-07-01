from fastapi import APIRouter, status, Body, Request, HTTPException
from urllib.parse import parse_qs

from waba_api.src.schemas.AmoSchemas import IncomingMessage
from waba_api.src.settings.conf import log
from waba_api.src.utils.amo.wh import (
    process_incoming_message,
    send_outgoing_message,
    get_user_id_by_lead_id,
)

router = APIRouter(prefix="/amo", tags=["amoCRM"])


@router.post("/webhook/incoming-message", status_code=status.HTTP_200_OK)
async def incoming_message_webhook(msg: IncomingMessage = Body(...)) -> dict:
    """
    Обрабатывает входящее сообщение (например, из WhatsApp).
    Создаёт или обновляет контакт и сделку в amoCRM.
    """
    try:
        await process_incoming_message(msg.external_user_id, msg.message)
        return {"status": "received"}
    except Exception as e:
        log.exception(f"Ошибка при обработке входящего сообщения: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.post("/send-message", status_code=status.HTTP_200_OK)
async def send_message(request: Request) -> dict:
    """
    Получает webhook из amoCRM с примечанием.
    Если это примечание в сделке — отправляет сообщение в WhatsApp.
    """
    try:
        raw_body = await request.body()
        if not raw_body:
            raise HTTPException(status_code=400, detail="Empty request body")

        body_str = raw_body.decode("utf-8")
        log.info(f"[AMO→Meta] RAW form body: {body_str}")

        form_data = parse_qs(body_str)
        meta = form_data.get('leads[note][0][note][metadata]')
        if meta and 'WhatsAppChat' in meta[0]:
            log.warning("[AMO→Meta] Пропущено сообщение от интеграции WhatsAppChat (чтобы не дублировать)")
            return {"status": "skipped"}

        if not any(key.startswith("leads[note]") for key in form_data.keys()):
            log.warning("[AMO→Meta] Пропущен нецелевой webhook — не является примечанием")
            return {"status": "skipped"}

        text = form_data.get("leads[note][0][note][text]", [None])[0]
        lead_id = form_data.get("leads[note][0][note][element_id]", [None])[0]

        if not text or not lead_id:
            raise HTTPException(status_code=400, detail="Missing note or lead_id")

        external_user_id = await get_user_id_by_lead_id(int(lead_id))
        success = await send_outgoing_message(external_user_id, text)

        return {"status": "sent" if success else "failed"}

    except HTTPException:
        raise
    except Exception as e:
        log.exception(f"[AMO→Meta] Ошибка в send-message: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
