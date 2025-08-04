from typing import Any, Dict, Optional, Tuple

import httpx

from src.settings.conf import log, metasettings


class MetaClient:
    def __init__(
        self,
        operator_number: str = metasettings.PHONE_NUMBER_ID,
        waba_id: str = metasettings.ACCOUNT_ID,
    ) -> None:
        self.base_url: str = metasettings.BASE_URL
        self.verify_token: str = metasettings.VERIFY_TOKEN
        self.token: str = metasettings.TOKEN
        self.operator_number: Optional[str] = operator_number
        self.headers: Dict[str, str] = metasettings.get_headers()
        self.bus_id: str = metasettings.BUS_ID
        self.waba_id: str = waba_id

    async def _response(self, method: str, url: str, **kwargs) -> Tuple[int, Any]:
        """Универсальный HTTP-запрос."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                request_method = getattr(client, method.lower())
                log.debug(f"[META] Sending {method} to {url} | Payload: {kwargs}")
                response = await request_method(url, headers=self.headers, **kwargs)

            log.debug(f"[META] Response {response.status_code}: {response.text}")
            return response.status_code, response.json()

        except httpx.RequestError as e:
            log.exception(f"[META] Request error: {str(e)}")
            return 503, {"error": str(e)}

        except Exception as e:
            log.exception(f"[META] Unexpected error: {str(e)}")
            return 500, {"error": str(e)}

    async def send_message(self, wa_id: str, text: str) -> Tuple[int, Any]:
        """Отправляет текстовое сообщение."""
        url = f"{self.base_url}/{self.operator_number}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": wa_id,
            "type": "text",
            "text": {"body": text},
        }
        return await self._response("POST", url, json=payload)

    async def post_template(
        self, wa_id: str, temp_name: str, temp_lang: str
    ) -> Tuple[int, Any]:
        """Отправляет шаблонное сообщение."""
        url = f"{self.base_url}/v19.0/{self.operator_number}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": wa_id,
            "type": "template",
            "template": {"name": temp_name, "language": {"code": temp_lang}},
        }
        return await self._response("POST", url, json=payload)

    async def get_templates(self) -> Tuple[int, list[Dict[str, Any]]]:
        """Получает список шаблонов."""
        url = f"{self.base_url}/v19.0/{self.waba_id}/message_templates?access_token={self.token}"
        status, data = await self._response("GET", url)

        if status != 200 or "data" not in data:
            log.error(f"[META] Ошибка получения шаблонов: {data}")
            return status, []

        templates_list = []
        for item in data.get("data", []):
            components = item.get("components", [])
            header = next(
                (c.get("text") for c in components if c["type"] == "HEADER"), None
            )
            body = next(
                (c.get("text") for c in components if c["type"] == "BODY"), None
            )
            footer = next(
                (c.get("text") for c in components if c["type"] == "FOOTER"), None
            )

            templates_list.append(
                {
                    "external_id": item["id"],
                    "name": item["name"],
                    "waba_category": item["category"],
                    "waba_language": item["language"],
                    "waba_header": header,
                    "content": body,
                    "waba_footer": footer,
                }
            )

        return 200, templates_list

    async def register_number(self, phone_data: Dict[str, Any]) -> Tuple[int, Any]:
        """Регистрирует новый номер телефона."""
        url = f"{self.base_url}/v18.0/{self.waba_id}/phone_numbers"
        log.info(f"[META] Registering phone number: {phone_data}")
        return await self._response("POST", url, json=phone_data)

    async def confirm_phone_number(
        self, phone_number_id: str, confirm_code: str
    ) -> Tuple[int, Any]:
        """Подтверждает номер по коду."""
        url = f"{self.base_url}/v18.0/{phone_number_id}/verify"
        log.info(f"[META] Confirming number {phone_number_id} with code {confirm_code}")
        return await self._response("POST", url, json={"code": confirm_code})
