from fastapi import APIRouter, HTTPException, Request, Response, status

from waba_api.src.settings.conf import log, metasettings
from waba_api.src.utils.amo.chat import AmoCRMClient
from waba_api.src.utils.meta.utils_message import send_message

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


@router.post("/amo_meta/send-message", status_code=200)
async def send_message_from_amo(request: Request) -> dict:
    from urllib.parse import parse_qs

    raw_body = await request.body()
    data = parse_qs(raw_body.decode("utf-8"))

    note_type = data.get("leads[note][0][note][note_type]", [""])[0]
    if note_type != "4":
        return {"status": "skipped"}

    text = data.get("leads[note][0][note][text]", [""])[0]
    lead_id = data.get("leads[note][0][note][element_id]", [""])[0]

    amo = AmoCRMClient()
    user_phone = amo.get_contact_phone_by_lead(int(lead_id))
    if not user_phone:
        raise HTTPException(400, "Телефон контакта не найден")

    await send_message(
        wa_id=user_phone,
        text=text,
        BASE_URL=metasettings.BASE_URL,
        PHONE_NUMBER=metasettings.PHONE_NUMBER_ID,
        HEADERS=metasettings.get_headers(),
        log=log,
        HTTPException=HTTPException,
        status=status
    )

    log.info(f"[AMO→WA] Сообщение отправлено клиенту {user_phone}: {text}")
    return {"status": "sent"}
