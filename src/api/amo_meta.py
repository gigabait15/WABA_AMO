import datetime
from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request

from waba_api.src.settings.conf import log
from waba_api.src.utils.amo.amo_chats_utils import AmoChats

router = APIRouter(prefix="/amo_meta", tags=["amo_meta"])


@router.post("/send-message", status_code=200)
async def send_message_from_amo(request: Request) -> dict:
    """
    Получает примечание от amoCRM и отправляет сообщение в чат amo.
    Поддерживает только примечания к сделкам (`note_type=4`).
    """
    try:
        raw_body = await request.body()
        if not raw_body:
            raise HTTPException(status_code=400, detail="Empty request body")

        body_str = raw_body.decode("utf-8")
        log.info(f"[AMO→Meta] RAW form body: {body_str}")

        form_data = parse_qs(body_str)

        # Фильтруем по "note_type" 4 — обычное текстовое примечание
        note_type = form_data.get("leads[note][0][note][note_type]", [""])[0]
        if note_type != "4":
            log.warning("[AMO→Meta] Пропущен нецелевой note_type")
            return {"status": "skipped"}

        text = form_data.get("leads[note][0][note][text]", [""])[0]
        lead_id = form_data.get("leads[note][0][note][element_id]", [""])[0]

        if not text or not lead_id:
            raise HTTPException(status_code=400, detail="Missing text or lead_id")

        log.info(f"[AMO→Meta] Новое сообщение из amoCRM по сделке {lead_id}: {text}")

        # Собираем данные для чата
        data = {
            "timestamp": int(datetime.datetime.now().timestamp()),
            "message_id": f"amo_{lead_id}_{datetime.datetime.now().timestamp()}",
            "conversation_id": str(lead_id),
            "user_id": "manager",
            "name": "Менеджер",
            "avatar_link": "",
            "message_text": text
        }

        await AmoChats().send_message_from_manager(data)
        return {"status": "sent"}

    except Exception as e:
        log.exception(f"[AMO→Meta] Ошибка в send-message: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
