import json
from typing import Any, Dict, Optional

import httpx

from src.schemas.MetaSchemas import PhoneNumber
from src.settings.conf import log, metasettings


class MetaClient:
    def __init__(self) -> None:
        self.base_url: str = metasettings.BASE_URL
        self.verify_token: str = metasettings.VERIFY_TOKEN
        self.token: str = metasettings.TOKEN
        self.operator_number: Optional[str] = metasettings.PHONE_NUMBER_ID
        self.headers: Dict[str, str] = metasettings.get_headers()
        self.bus_id: str = metasettings.BUS_ID
        self.waba_id: str = metasettings.ACCOUNT_ID

    def get_operator_number(self, operator_number: Optional[str]) -> str:
        """
        Получение operator_number. Если не передан, используется значение из настроек.

        :param operator_number: Номер телефона оператора (может быть None)
        :return: Строка с phone_number_id
        """
        self.operator_number = operator_number or metasettings.PHONE_NUMBER_ID
        return self.operator_number

    async def _response(self, method: str, url: str, **kwargs) -> Dict[str, Any]:
        """
        Универсальный метод отправки HTTP-запросов с обработкой ошибок.

        :param method: HTTP метод ('GET', 'POST', ...)
        :param url: URL запроса
        :param kwargs: дополнительные параметры (json, params и т.д.)
        :return: JSON-ответ от Meta API как dict
        :raises: Exception с текстом ошибки
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                request_method = getattr(client, method.lower())
                log.debug(f"[META] Sending {method} request to {url} with {kwargs}")
                response = await request_method(url, headers=self.headers, **kwargs)

            if response.status_code >= 400:
                log.error(f"[META] Request failed: {response.status_code} - {response.text}")
                raise Exception(f"[META] Error: {response.text}")

            log.debug(f"[META] Response from {url}: {response.text}")
            return response.json()

        except httpx.RequestError as e:
            log.exception(f"[META] Request error: {str(e)}")
            raise Exception(f"[META] Request error: {str(e)}")

        except Exception as e:
            log.exception(f"[META] Unexpected error: {str(e)}")
            raise

    # TODO добавить поддержку отправки медиа
    async def send_message(self, wa_id: str, text: str) -> Dict[str, Any]:
        """
        Отправляет текстовое сообщение пользователю WhatsApp.
        :param wa_id: WhatsApp ID получателя (строка вида «628123456789»).
        :param text: Текст сообщения (UTF-8, до 4096 символов).
        :return: JSON-ответ Cloud API.
        """
        url = f"{self.base_url}/{self.operator_number}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": wa_id,
            "type": "text",
            "text": {"body": text},
        }
        return await self._response("POST", url, json=payload)

    async def get_templates(self, **kwargs):
        try:
            url = f"{self.base_url}/v19.0/{self.waba_id}/message_templates?access_token={self.token}"

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url)

            if response.status_code != 200:
                log.error(f"Ошибка получения шаблонов: {response.text}")
                raise kwargs['HTTPException'](
                    status_code=response.status_code,
                    detail="Ошибка Meta API"
                )

            response_obj = kwargs['responses'].JSONResponse(
                status_code=200,
                content=response.json()
            )
            templates_list = []

            for item in json.loads(response_obj.body).get('data', []):
                components = item.get('components', [])
                header = next((c.get('text') for c in components if c['type'] == 'HEADER'), None)
                body = next((c.get('text') for c in components if c['type'] == 'BODY'), None)
                footer = next((c.get('text') for c in components if c['type'] == 'FOOTER'), None)

                templates_list.append({
                    'external_id': item['id'],
                    'name': item['name'],
                    'waba_category': item['category'],
                    'waba_language': item['language'],
                    'waba_header': header,
                    'content': body,
                    'waba_footer': footer
                })

            return templates_list

        except httpx.RequestError as e:
            log.error(f"Ошибка подключения: {str(e)}")
            raise kwargs['HTTPException'](status_code=503, detail="Ошибка подключения к Meta API")
        except Exception as e:
            log.exception("Неизвестная ошибка при получении шаблонов")
            raise kwargs['HTTPException'](status_code=500, detail=f"Внутренняя ошибка: {str(e)}")

    async def get_display_phone_number(self, phone_number_id: str) -> str:
        """
        Получить номер телефона по его ID.

        :param phone_number_id: ID номера телефона
        :return: Отображаемый номер телефона (str)
        """
        url = f"{self.base_url}/v17.0/{phone_number_id}"
        params = {"fields": "display_phone_number"}
        data = await self._response('POST', url, params=params)
        return data.get("display_phone_number", "")

    async def get_owned_whatsapp_business_accounts(self) -> Dict[str, Any]:
        """
        Получить список WhatsApp Business аккаунтов, связанных с текущим бизнесом.

        :return: JSON-ответ от Meta
        """
        url = f"{self.base_url}/v17.0/{self.bus_id}/owned_whatsapp_business_accounts"
        return await self._response('GET', url)

    async def register_number(self, phone_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Зарегистрировать новый номер телефона в WABA.

        :param phone_data: Словарь с данными номера (cc, phone_number, display_name, verified_name)
        :return: Ответ Meta с phone_id или описание ошибки
        """
        url = f"{self.base_url}/v18.0/{self.waba_id}/phone_numbers"
        log.info(f"[META] Registering phone number: {phone_data}")
        return await self._response('POST', url, json=phone_data)

    async def confirm_phone_number(self, phone_number_id: str, confirm_code: str) -> Dict[str, Any]:
        """
        Подтвердить номер телефона с помощью OTP-кода, полученного от Meta.

        :param phone_number_id: ID номера, который нужно подтвердить
        :param confirm_code: Одноразовый код (OTP)
        :return: {"success": true} или описание ошибки
        """
        url = f"{self.base_url}/v18.0/{phone_number_id}/verify"
        log.info(f"[META] Confirming phone number {phone_number_id} with code {confirm_code}")
        return await self._response('POST', url, json={"code": confirm_code})