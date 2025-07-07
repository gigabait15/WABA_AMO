import hashlib
import hmac
import json

from fastapi import APIRouter, HTTPException, Request, Response, status

from src.settings.conf import log, metasettings
from src.utils.amo.chat import AmoCRMClient

from waba_api.src.settings.conf import chatsettings

router = APIRouter(prefix="/amo", tags=["amoCRM"])


@router.post("/webhook/incoming-message", status_code=status.HTTP_200_OK)
async def incoming_message_webhook(request: Request):
    try:
        raw_body = await request.body()
        signature = request.headers.get("X-Signature", "")

        computed_signature = hmac.new(
            key=chatsettings.AMO_CHATS_SECRET.encode(),
            msg=raw_body,
            digestmod=hashlib.sha1
        ).hexdigest()

        if signature != computed_signature:
            log.warning("[AMO→Webhook] Подпись не прошла проверку")
            return Response(status_code=403, content="Invalid signature")

        payload = json.loads(raw_body)
        message_data = payload.get("message", {})
        message = message_data.get("message", {})
        sender = message_data.get("sender", {})
        receiver = message_data.get("receiver", {})

        chat_id = message_data.get("conversation", {}).get("client_id")
        text = message.get("text")
        msg_type = message.get("type")
        timestamp = payload.get("time")
        message_id = message.get("id")

        is_from_manager = True if "ref_id" not in sender else False

        if is_from_manager:
            log.info(f"[AMO→Client] Менеджер написал в чат {chat_id}: {text}")

            # await send_message(chat_id, text)

        else:
            log.info(f"[Client→AMO] Клиент написал: {text}")

    except Exception as e:
        log.exception(f"[AMO→Webhook] Ошибка обработки: {e}")
        return Response(status_code=500, content="Internal error")

    return Response(status_code=200, content="OK")


@router.post("/webhook/send-message", status_code=200)
async def send_message_from_amo(request: Request) -> dict:
    from urllib.parse import parse_qs

    raw_body = await request.body()
    data = parse_qs(raw_body.decode("utf-8"))

    note_type = data.get("leads[note][0][note][note_type]", [""])[0]
    if note_type != "4":
        return {"status": "skipped"}

    text = data.get("leads[note][0][note][text]", [""])[0]
    lead_id = data.get("leads[note][0][note][element_id]", [""])[0]

    log.info('[AMoO] Send message amo %s', data)

    amo = AmoCRMClient()
    user_phone = amo.get_contact_phone_by_lead(int(lead_id))
    if not user_phone:
        raise HTTPException(400, "Телефон контакта не найден")


    log.info(f"[AMO→WA] Сообщение отправлено клиенту {user_phone}: {text}")
    return {"status": "sent"}
