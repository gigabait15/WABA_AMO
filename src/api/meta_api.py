from __future__ import annotations

import datetime
import json
import httpx
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, responses, status, BackgroundTasks

from waba_api.src.database.DAO.crud import MessagesDAO
from waba_api.src.schemas.MetaSchemas import SendRequest, TemplateSendRequest
from waba_api.src.settings.conf import log, metasettings
from waba_api.src.tasks.amo import send_to_amo
from waba_api.src.utils.meta.utils_message import get_display_phone_number, send_message


db = MessagesDAO()
router = APIRouter(prefix='/meta', tags=['meta'])



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
async def incoming(request: Request, background_tasks: BackgroundTasks) -> str:
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

    if payload.get('object') == "whatsapp_business_account":
        data = payload.get('entry')[0]
        changes = data['changes'][0]
        value = changes.get('value')

        # TODO Сообщение от пользователя
        if value.get('contacts') is not None:
            user_number = value.get('messages')[0].get('from')
            operator_number = value.get('metadata').get('display_phone_number')
            date = value.get('messages')[0].get('timestamp')
            dt_obj = datetime.datetime.fromtimestamp(int(date))
            if value.get('messages')[0].get('type') == "text":
                text = value.get('messages')[0].get('text').get('body')
                log.info('New message %s from %s to %s: %s ', dt_obj, user_number, operator_number, text)

                await db.add(
                    user_number=int(user_number),
                    operator_number=int(operator_number),
                    from_number=int(user_number),
                    text=text,
                    date=dt_obj
                )

                background_tasks.add_task(
                    send_to_amo,
                    external_user_id=user_number,
                    text=text,
                    log=log
                )

        # TODO Сообщение отправенное пользователю
        else:
            user_number = value.get('statuses')[0].get('recipient_id')
            operator_number = value.get('metadata').get('display_phone_number')
            date = value.get('statuses')[0].get('timestamp')
            dt_obj = datetime.datetime.fromtimestamp(int(date))
            message_status = value.get('statuses')[0].get('status')
            log.info('Meta message %s from %s to %s status %s ', dt_obj, operator_number, user_number, message_status)

    return "ok"


@router.post("/send", status_code=status.HTTP_200_OK)
async def send(send_req: SendRequest = Depends()) -> str:
    """
    Отправляет сообщение пользователю.
    Args:
        send_req: валидированная модель `SendRequest` (Pydantic).
    Returns:
        JSON-ответ, проброшенный от Cloud API.
    Raises:
        HTTPException 502: если Cloud API вернула ошибку или не ответила.
    """
    await send_message(
        send_req.wa_id,
        send_req.text,
        BASE_URL=metasettings.BASE_URL,
        PHONE_NUMBER=metasettings.PHONE_NUMBER_ID,
        HEADERS=metasettings.get_headers(),
        log=log,
        HTTPException=HTTPException,
        status=status
    )

    operator_number = await get_display_phone_number(metasettings.PHONE_NUMBER_ID, metasettings.TOKEN)
    dt = datetime.datetime.now()
    log.info('%s: message from %s to %s text %s', dt, operator_number, send_req.wa_id, send_req.text)

    await db.add(
        user_number=int(send_req.wa_id),
        operator_number=int(operator_number),
        from_number=int(operator_number),
        text=send_req.text,
        date=dt
    )

    return 'ok'


@router.get(
    "/number",
    response_model=Any,
    status_code=status.HTTP_200_OK,
    summary="Получить номера телефонов из WABA",
    description="Получает список номеров телефонов, привязанных к WhatsApp Business Account через Graph API Meta"
)
async def get_number() -> responses.JSONResponse:
    """
    Получает WABA ID по Business ID, а затем возвращает номера телефонов,
    связанные с этим WhatsApp Business Account.
    Returns:
        responses.JSONResponse: Список номеров в формате JSON или ошибка с кодом и сообщением.
    """

    try:
        waba_url = (
            f'{metasettings.BASE_URL}/v19.0/{metasettings.BUS_ID}/'
            f'owned_whatsapp_business_accounts?access_token={metasettings.TOKEN}'
        )

        async with httpx.AsyncClient(timeout=10.0) as client:
            waba_response: httpx.Response = await client.get(waba_url)

        if waba_response.status_code != 200:
            log.error(f"Ошибка при получении WABA: {waba_response.text}")
            raise HTTPException(
                status_code=waba_response.status_code,
                detail="Не удалось получить WhatsApp Business Account"
            )

        waba_data = waba_response.json().get("data")
        if not waba_data:
            raise HTTPException(status_code=404, detail="WABA аккаунты не найдены")

        waba_id = waba_data[0].get("id")
        if not waba_id:
            raise HTTPException(status_code=500, detail="Ошибка при получении ID WABA")

        numbers_url = (
            f"{metasettings.BASE_URL}/v19.0/{waba_id}/phone_numbers?access_token={metasettings.TOKEN}"
        )

        async with httpx.AsyncClient(timeout=10.0) as client:
            num_response: httpx.Response = await client.get(numbers_url)

        if num_response.status_code != 200:
            log.error(f"Ошибка при получении номеров: {num_response.text}")
            raise HTTPException(
                status_code=num_response.status_code,
                detail="Не удалось получить номера телефонов"
            )

        return responses.JSONResponse(status_code=200, content=num_response.json())

    except httpx.RequestError as e:
        log.error(f"Ошибка подключения: {str(e)}")
        raise HTTPException(status_code=503, detail="Ошибка подключения к Meta API")

    except Exception as e:
        log.exception("Неизвестная ошибка")
        raise HTTPException(status_code=500, detail=f"Внутренняя ошибка сервера: {str(e)}")

@router.get(
    "/templates",
    response_model=Any,
    status_code=status.HTTP_200_OK,
    summary="Получить шаблоны сообщений",
    description="Возвращает список одобренных шаблонов сообщений для текущего WhatsApp Business Account"
)
async def get_templates() -> responses.JSONResponse:
    try:
        waba_id = metasettings.ACCOUNT_ID
        url = f"{metasettings.BASE_URL}/v19.0/{waba_id}/message_templates?access_token={metasettings.TOKEN}"

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)

        if response.status_code != 200:
            log.error(f"Ошибка получения шаблонов: {response.text}")
            raise HTTPException(status_code=response.status_code, detail="Ошибка Meta API")

        return responses.JSONResponse(status_code=200, content=response.json())

    except httpx.RequestError as e:
        log.error(f"Ошибка подключения: {str(e)}")
        raise HTTPException(status_code=503, detail="Ошибка подключения к Meta API")
    except Exception as e:
        log.exception("Неизвестная ошибка при получении шаблонов")
        raise HTTPException(status_code=500, detail=f"Внутренняя ошибка: {str(e)}")


@router.post(
    "/send_template",
    status_code=status.HTTP_200_OK,
    summary="Отправить шаблонное сообщение",
    description="Отправляет предварительно одобренное шаблонное сообщение пользователю"
)
async def send_template_message(payload: TemplateSendRequest = Depends()) -> responses.JSONResponse:
    try:
        url = f"{metasettings.BASE_URL}/v19.0/{metasettings.PHONE_NUMBER_ID}/messages"

        headers = metasettings.get_headers()

        data = {
            "messaging_product": "whatsapp",
            "to": payload.to,
            "type": "template",
            "template": {
                "name": payload.template_name,
                "language": {"code": payload.language_code}
            }
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, headers=headers, json=data)
            # TODO добвавить БД

        if response.status_code != 200:
            log.error(f"Ошибка при отправке шаблона: {response.text}")
            raise HTTPException(status_code=response.status_code, detail="Не удалось отправить сообщение")

        return responses.JSONResponse(status_code=200, content=response.json())

    except httpx.RequestError as e:
        log.error(f"Ошибка подключения: {str(e)}")
        raise HTTPException(status_code=503, detail="Ошибка подключения к Meta API")
    except Exception as e:
        log.exception("Неизвестная ошибка при отправке шаблона")
        raise HTTPException(status_code=500, detail=f"Внутренняя ошибка: {str(e)}")

