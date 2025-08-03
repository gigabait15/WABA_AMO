from __future__ import annotations

import datetime
import json
from typing import Any, Dict, List

import httpx
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
    responses,
    status,
)

from src.database.DAO.crud import DealsDAO, MessagesDAO
from src.schemas.MetaSchemas import (
    PhoneNumber,
    SendRequest,
    SuccessPhoneNumber,
    TemplateSendRequest,
    TestR,
)
from src.settings.conf import log, metasettings
from src.utils.amo.chat import AmoCRMClient
from src.utils.meta.utils_message import MetaClient
from src.utils.rmq.RabbitModel import rmq

from src.utils.redis_conn import redis_client

from src.schemas.MetaSchemas import MessageOut

db = MessagesDAO()
service = MetaClient()
messagesDAO = MessagesDAO()
dealsDAO = DealsDAO()
router = APIRouter(prefix="/meta", tags=["meta"])


@router.get(
    "/webhook",
    response_class=responses.PlainTextResponse,
    status_code=status.HTTP_200_OK,
)
async def verify(
    mode: str | None = Query(None, alias="hub.mode"),
    token: str | None = Query(None, alias="hub.verify_token"),
    challenge: str | None = Query(None, alias="hub.challenge"),
) -> Response:
    """
    Проверка webhook-а Meta.
    При первой настройке Meta Cloud API посылает GET-запрос с параметрами:
    * **hub.mode** — должен быть `subscribe`;
    * **hub.verify_token** — должен совпадать с придуманным вами токеном;
    * **hub.challenge** — нужно вернуть это значение как plaintext.
    Returns:
        PlainTextResponse с hub.challenge при успехе.
    Raises:
        HTTPException 403: если проверка не пройдена.
    """
    if mode == "subscribe" and token == metasettings.VERIFY_TOKEN and challenge:
        return responses.PlainTextResponse(content=challenge, status_code=200)

    log.warning(
        "Webhook verification failed: mode=%s token=%s challenge=%s",
        mode,
        token,
        bool(challenge),
    )
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/webhook", status_code=status.HTTP_200_OK)
async def incoming(request: Request) -> str:
    """
    Обрабатывает входящие сообщения от Cloud API.
    * Парсим JSON-payload;
    * Передаём в `parse_wa_messages`;
    * Кладём результат в IN_MEMORY_HISTORY или БД;
    * Логируем текстовые сообщения.
    Returns:
        `"ok"` — если всё прошло без ошибок.
    Raises:
        HTTPException 400: неверный JSON.
    """
    try:
        payload: Dict[str, Any] = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Malformed JSON body")

    if payload.get("object") == "whatsapp_business_account":
        data = payload.get("entry")[0]
        changes = data["changes"][0]
        value = changes.get("value")

        # TODO Сообщение от пользователя
        if value.get("contacts") is not None:
            user_number = value.get("messages")[0].get("from")
            operator_number = value.get("metadata").get("display_phone_number")
            date = value.get("messages")[0].get("timestamp")
            dt_obj = datetime.datetime.fromtimestamp(int(date))
            if value.get("messages")[0].get("type") == "text":
                text = value.get("messages")[0].get("text").get("body")
                log.info(
                    "New message %s from %s to %s: %s ",
                    dt_obj,
                    user_number,
                    operator_number,
                    text,
                )
                await rmq.publish_to_chat(f'{user_number}-{operator_number}', text)

                client = AmoCRMClient()
                await client.ensure_chat_visible(
                    phone=user_number,
                    text=text,
                    timestamp=date,
                    operator_phone=operator_number,
                )

                deal_id = await dealsDAO.find_id(
                    client_phone=user_number,
                    operator_phone=operator_number,
                )

                await messagesDAO.add(
                    id=value.get("messages")[0].get("id"),
                    sender=user_number,
                    text=text,
                    timestamp=dt_obj,
                    deals_id=deal_id,
                )

        # TODO Сообщение отправенное пользователю
        else:
            user_number = value.get("statuses")[0].get("recipient_id")
            operator_number = value.get("metadata").get("display_phone_number")
            date = value.get("statuses")[0].get("timestamp")
            dt_obj = datetime.datetime.fromtimestamp(int(date))
            message_status = value.get("statuses")[0].get("status")

            log.info(f"[---------META] {value}")

            deal_id = await dealsDAO.find_id(
                client_phone=user_number,
                operator_phone=operator_number,
            )

            raw_data = await redis_client.lpop("amo_to_meta")

            await rmq.publish_to_chat(f'{user_number}-{operator_number}', json.loads(raw_data))

            await messagesDAO.upsert(
                id=value.get("statuses")[0].get("id"),
                sender=user_number,
                text=json.loads(raw_data),
                timestamp=dt_obj,
                deals_id=deal_id,
                status=message_status,
            )

            log.info(
                "Meta message %s from %s to %s status %s ",
                dt_obj,
                operator_number,
                user_number,
                message_status,
            )

    return "ok"


@router.post("/test_meta")
async def test_meta(test_mess: TestR = Depends()):
    client = AmoCRMClient()
    await client.ensure_chat_visible(
        phone=test_mess.wa_id,
        text=test_mess.text,
        timestamp=int(datetime.datetime.now().timestamp()),
        operator_phone=test_mess.oper_num,
    )
    return "ok"


@router.post("/send", status_code=status.HTTP_200_OK)
async def send(send_req: SendRequest = Depends()) -> str:
    """
    Отправляет сообщение пользователю.
    :param send_req: валидированная модель `SendRequest` (Pydantic).
    :return: JSON-ответ, проброшенный от Cloud API.
    """
    await service.send_message(wa_id=send_req.wa_id, text=send_req.text)
    # TODO здесь можно из БД прокидывать

    return "ok"


@router.get(
    "/number",
    response_model=Any,
    status_code=status.HTTP_200_OK,
    summary="Получить номера телефонов из WABA",
    description="Получает список номеров телефонов, привязанных к WhatsApp Business Account через Graph API Meta",
)
async def get_number() -> responses.JSONResponse:
    """
    Получает WABA ID по Business ID, а затем возвращает все номера телефонов,
    связанные с этим WhatsApp Business Account.
    :return: Список номеров в формате JSON или ошибка с кодом и сообщением.
    """
    try:
        waba_url = (
            f"{metasettings.BASE_URL}/v23.0/{metasettings.BUS_ID}/"
            f"owned_whatsapp_business_accounts?access_token={metasettings.TOKEN}"
        )

        async with httpx.AsyncClient(timeout=10.0) as client:
            waba_response = await client.get(waba_url)

        if waba_response.status_code != 200:
            log.error(f"Ошибка при получении WABA: {waba_response.text}")
            raise HTTPException(
                status_code=waba_response.status_code,
                detail="Не удалось получить WhatsApp Business Account",
            )

        waba_data = waba_response.json().get("data")
        if not waba_data:
            raise HTTPException(status_code=404, detail="WABA аккаунты не найдены")

        all_phone_numbers = []

        async with httpx.AsyncClient(timeout=10.0) as client:
            for waba in waba_data:
                waba_id = waba.get("id")
                if not waba_id:
                    continue

                numbers_url = f"{metasettings.BASE_URL}/v19.0/{waba_id}/phone_numbers?access_token={metasettings.TOKEN}"
                num_response = await client.get(numbers_url)

                if num_response.status_code == 200:
                    num_data = num_response.json().get("data", [])
                    all_phone_numbers.extend(num_data)
                else:
                    log.warning(
                        f"Не удалось получить номера для WABA ID {waba_id}: {num_response.text}"
                    )

        return responses.JSONResponse(
            status_code=200, content={"data": all_phone_numbers}
        )

    except httpx.RequestError as e:
        log.error(f"Ошибка подключения: {str(e)}")
        raise HTTPException(status_code=503, detail="Ошибка подключения к Meta API")

    except Exception as e:
        log.exception("Неизвестная ошибка")
        raise HTTPException(
            status_code=500, detail=f"Внутренняя ошибка сервера: {str(e)}"
        )


@router.get(
    "/templates",
    response_model=Any,
    status_code=status.HTTP_200_OK,
    summary="Получить шаблоны сообщений",
    description="Возвращает список одобренных шаблонов сообщений для текущего WhatsApp Business Account",
)
async def get_templates() -> responses.JSONResponse:
    return await service.get_templates()


@router.post(
    "/send_template",
    status_code=status.HTTP_200_OK,
    summary="Отправить шаблонное сообщение",
    description="Отправляет предварительно одобренное шаблонное сообщение пользователю",
)
async def send_template_message(
    payload: TemplateSendRequest = Depends(),
) -> responses.JSONResponse:
    return await service.post_template(
        wa_id=payload.to,
        temp_name=payload.template_name,
        language_code=payload.language_code,
    )


@router.post(
    "/register_number",
    status_code=status.HTTP_200_OK,
    summary="Регистрация нового номера телефона",
    description="Добавление нового телефона в бизнес аккаунт. ответ будет id нового номера",
)
async def register_number(
    phone_data: PhoneNumber = Depends(),
) -> responses.JSONResponse:
    payload = {
        "cc": phone_data.cc,
        "phone_number": phone_data.phone_number,
        "display_name": phone_data.display_name,
        "verified_name": phone_data.verified_name,
    }
    return service.register_number(payload)


@router.post(
    "/success_number",
    status_code=status.HTTP_200_OK,
    summary="Подтверждение номера телефона",
    description="После регистрации на указанный номер придет смс, ее вместе с phone_id"
    " нужно передать сюда для подтвержения номера",
)
async def success_number(
    phone_data: SuccessPhoneNumber = Depends(),
) -> responses.JSONResponse:
    return service.confirm_phone_number(
        phone_number_id=phone_data.phone_number_id, confirm_code=phone_data.confirm_code
    )


@router.get(
    "/history",
    status_code=status.HTTP_200_OK,
    summary="Получение истории сообщений",
    description="Запрос на получение истории сообщений клиента по связке клиент-оператор",
    response_model=List[MessageOut]
)
async def get_history(
    client_phone: str = Query(..., description="Телефон клиента"),
    operator_phone: str = Query(..., description="Телефон оператора"),
):
    deal = dealsDAO.find_by_phones(client_phone, operator_phone)

    if not deal:
        raise HTTPException(
            status_code=404,
            detail="Связка клиент-оператор не найдена"
        )
    messages = messagesDAO.get_message_by_deal(deal.id)
    return messages