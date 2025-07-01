import json
from typing import Any, Dict

import httpx


# TODO добавить поддержку отправки медиа
async def send_message(wa_id: str, text: str, **kwargs) -> Dict[str, Any]:
    """
    Отправляет текстовое сообщение пользователю WhatsApp.
    Args:
        wa_id: WhatsApp ID получателя (строка вида «628123456789»).
        text: Текст сообщения (UTF-8, до 4096 символов).
    Returns:
        JSON-ответ Cloud API.
    Raises:
        HTTPException: 502 ― если сторонний сервис вернул 4xx/5xx.
    """
    url = f"{kwargs['BASE_URL']}/{kwargs['PHONE_NUMBER']}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": wa_id,
        "type": "text",
        "text": {"body": text},
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response: httpx.Response = await client.post(
                url, json=payload, headers=kwargs['HEADERS']
            )
    except httpx.RequestError as exc:
        kwargs['log'].exception("Network error while sending message")
        raise kwargs['HTTPException'](
            status_code=kwargs['status'].HTTP_502_BAD_GATEWAY,
            detail=f"Network error: {exc}",
        ) from exc

    if response.status_code >= 400:
        kwargs['log'].error("Cloud API error %s → %s", response.status_code, response.text)
        raise kwargs['HTTPException'](
            status_code=kwargs['status'].HTTP_502_BAD_GATEWAY,
            detail=f"Cloud API error: {response.status_code}",
        )

    try:
        return response.json()
    except json.JSONDecodeError as exc:
        kwargs['log'].exception("Invalid JSON from Cloud API")
        raise kwargs['HTTPException'](
            status_code=kwargs['status'].HTTP_502_BAD_GATEWAY,
            detail="Invalid JSON from Cloud API",
        ) from exc


async def get_display_phone_number(phone_number_id: str, access_token: str) -> str:
    url = f"https://graph.facebook.com/v17.0/{phone_number_id}"
    params = {"fields": "display_phone_number"}
    headers = {"Authorization": f"Bearer {access_token}"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url, params=params, headers=headers)

    if response.status_code >= 400:
        raise Exception(f"Failed to get display phone number: {response.text}")

    data = response.json()
    return data.get("display_phone_number", "")
