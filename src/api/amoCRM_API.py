import json
from urllib.parse import parse_qs, unquote_plus

from fastapi import APIRouter, HTTPException, Query, Request, Response, status

from src.database.DAO.crud import DealsDAO, MessagesDAO
from src.settings.conf import log, metasettings
from src.utils.amo.chat import AmoCRMClient, incoming_message, send_message
from src.utils.meta.utils_message import MetaClient
from src.utils.rmq.RabbitModel import rmq
from waba_api.src.schemas.AmoSchemas import TemplateSchemas

router = APIRouter(prefix="/amo", tags=["amoCRM"])
amo = AmoCRMClient()
metaservice = MetaClient()
messagesDAO = MessagesDAO()
dealsDAO = DealsDAO()


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
        print(
            "📭 AmoCRM Webhook (FORM):",
            json.dumps(parsed, indent=2, ensure_ascii=False),
        )
    else:
        raw = await request.body()
        print("⚠️ Unknown content-type:", content_type)
        print("🔍 Raw body:", raw.decode())

    return {"status": "ok"}


@router.post("/webhook/incoming-message", status_code=status.HTTP_200_OK)
async def incoming_message_webhook(request: Request):
    (
        message_data,
        message,
        sender,
        receiver,
        chat_id,
        text,
        msg_type,
        timestamp,
        message_id,
    ) = await incoming_message(request)
    is_from_manager = True if "ref_id" not in sender else False
    is_template = True if message.get("template") else False
    temp_id = message.get("template").get("external_id") if is_template else None

    await rmq.send_message("webhook_messages", f"meta:{message_data}")

    if is_from_manager:
        try:
            await send_message(temp_id, chat_id, text, receiver.get("phone"))
            log.info(f"[AMO ----]  {message_data}\n {message_id}")

        except Exception as e:
            log.exception(f"[AMO→Webhook] Ошибка обработки: {e}")
            return Response(status_code=500, content="Internal error")
    else:
        log.info(f"[Client→AMO] Клиент написал: {text}")

    return Response(status_code=200, content="OK")


@router.post("/webhook/send-message", status_code=200)
async def send_message_from_amo(request: Request) -> dict:
    raw_body = await request.body()
    data = parse_qs(raw_body.decode("utf-8"))

    note_type = data.get("leads[note][0][note][note_type]", [""])[0]
    if note_type != "4":
        return {"status": "skipped"}

    text = data.get("leads[note][0][note][text]", [""])[0]
    lead_id = data.get("leads[note][0][note][element_id]", [""])[0]

    log.info("[AMO] Send message amo %s", data)
    log.info("Ручка send_message AMO")

    user_phone = amo.get_contact_phone_by_lead(int(lead_id))
    if not user_phone:
        raise HTTPException(400, "Телефон контакта не найден")

    log.info(f"[AMO→WA] Сообщение отправлено клиенту {user_phone}: {text}")
    return {"status": "sent"}


@router.get("/get_templates")
async def get_templates():
    return await amo.get_templates()


@router.get("/get_template/{template_id}")
async def get_template(template_id: str):
    return await amo.get_template_by_id(template_id)


@router.post("/add_template")
async def add_template():
    meta_status, meta_templates = await metaservice.get_templates()
    for temp in meta_templates:
        await amo.add_template(TemplateSchemas(**temp).dict())


@router.post("/test_create_chat")
async def test_create_chat(t_id: int = Query(..., description="id")):
    return await TemplatesDAO.find_item_by_id(t_id)
