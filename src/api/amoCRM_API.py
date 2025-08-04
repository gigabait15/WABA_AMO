import json
from urllib.parse import parse_qs, unquote_plus

from fastapi import APIRouter, HTTPException, Request, Response, status, Depends

from src.database.DAO.crud import DealsDAO, MessagesDAO
from src.settings.conf import log, metasettings
from src.utils.amo.chat import AmoCRMClient, incoming_message, send_message
from src.utils.meta.utils_message import MetaClient
from src.utils.rmq.RabbitModel import get_rmq_dependency, callback_wrapper, AsyncRabbitMQRepository
from src.schemas.AmoSchemas import TemplateSchemas
from src.utils.redis_conn import redis_client

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


@router.post("/webhook/incoming-message/{scope_id}", status_code=status.HTTP_200_OK)
async def incoming_message_webhook(scope_id: str, request: Request, rmq: AsyncRabbitMQRepository = Depends(get_rmq_dependency)):
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

    await rmq.send_message("queue_name", json.dumps({
        "chat_id": chat_id,
        "text": text,
        "sender": sender,
        "receiver": receiver,
        "timestamp": timestamp,
    }))

    log.info(f"[AMO → RMQ] Отправлено: {message_data}\nMessage ID: {message_id}")

    if is_from_manager:
        try:
            await send_message(temp_id, chat_id, text, receiver.get("phone"))
            log.info(f"[AMO ----]  {message_data}\n {message_id}")
            await redis_client.rpush(f"{receiver.get("phone")}", json.dumps({"text": text}))

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


@router.get("/leads/{lead_id}/chat_id")
async def get_chat_id_by_lead_id(lead_id: int):
    try:
        phone = await amo.get_contact_phone_by_lead(lead_id)
        if not phone:
            raise HTTPException(status_code=404, detail="Контакт или телефон не найден")

        operator_key = f"client_operator:{phone}"
        operator_phone = await redis_client.get(operator_key)
        if not operator_phone:
            raise HTTPException(status_code=404, detail="Оператор не найден в Redis")
        if isinstance(operator_phone, bytes):
            operator_phone = operator_phone.decode()

        chat_id = await redis_client.get_chat_id(phone, operator_phone)
        if not chat_id:
            raise HTTPException(status_code=404, detail="chat_id не найден")

        return {"lead_id": lead_id, "phone": phone, "operator": operator_phone, "chat_id": chat_id}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка сервера: {str(e)}")
