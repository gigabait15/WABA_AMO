import hashlib
import hmac
import json
import os
from urllib.parse import unquote_plus, parse_qs

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse

from src.settings.conf import log, metasettings
from src.utils.amo.chat import AmoCRMClient

from waba_api.src.settings.conf import chatsettings
from src.utils.meta.utils_message import MetaClient

router = APIRouter(prefix="/amo", tags=["amoCRM"])
metaservice = MetaClient()


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_FILE = os.path.join(BASE_DIR, "install.html")
@router.get("/", response_class=HTMLResponse)
async def get_amo():
    with open(HTML_FILE, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@router.post("/webhook")
async def receive_amocrm_webhook(request: Request):
    content_type = request.headers.get("content-type", "")

    if "application/json" in content_type:
        body = await request.json()
        print("📩 AmoCRM Webhook (JSON):", body)
    elif "application/x-www-form-urlencoded" in content_type:
        form_data = await request.body()
        decoded = unquote_plus(form_data.decode())
        parsed = parse_qs(decoded)
        print("📭 AmoCRM Webhook (FORM):", json.dumps(parsed, indent=2, ensure_ascii=False))
    else:
        raw = await request.body()
        print("⚠️ Unknown content-type:", content_type)
        print("🔍 Raw body:", raw.decode())

    return {"status": "ok"}


from fastapi import Request, Response, status
from urllib.parse import parse_qs
import json

@router.post("/webhook/incoming-message", status_code=status.HTTP_200_OK)
async def incoming_message_webhook(request: Request):
    try:
        if request.headers.get("Content-Type", "").startswith("application/json"):
            raw_body = await request.body()
            signature = request.headers.get("X-Signature", "")
            log.info("Received AmoCRM Webhook message (raw_body): %s", raw_body)
            log.info("Received AmoCRM Webhook message (signature): %s", signature)

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
                phone_client = chat_id.split(':')[1]
                if phone_client[0] == '7':
                    ru_client = '8' + phone_client[1:]
                    log.info(f"[AMO] Chat ID: {ru_client}")
                    await metaservice.send_message(ru_client, text)
                else:
                    await metaservice.send_message(phone_client, text)
            else:
                log.info(f"[Client→AMO] Клиент написал: {text}")
        else:
            # Handle form-urlencoded — just log it for now or parse with parse_qs
            raw_body = await request.body()
            log.info("📭 AmoCRM Webhook (FORM): %s", raw_body.decode())
            # parsed_form = parse_qs(raw_body.decode())
            # log.debug(parsed_form)

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
