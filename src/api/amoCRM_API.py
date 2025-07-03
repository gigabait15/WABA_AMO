from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request, Response, status

from waba_api.src.settings.conf import log
from waba_api.src.utils.amo.wh import get_user_id_by_lead_id, send_outgoing_message

router = APIRouter(prefix="/amo", tags=["amoCRM"])


@router.post("/webhook/incoming-message", status_code=status.HTTP_200_OK)
async def incoming_message_webhook(request: Request):
    """
    Обрабатывает входящее уведомление от amoCRM.
    """
    try:
        form = await request.form()
        log.info(f"[AMO→Meta] Webhook received (form): {dict(form)}")
    except Exception as e:
        log.exception(f"[AMO→Meta] Error processing webhook {e}")
    return Response(content="Webhook ignored", status_code=200)


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
