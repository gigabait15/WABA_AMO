import hashlib
import hmac
import json
from datetime import datetime
from email.utils import format_datetime
from typing import Optional, Tuple

import httpx

from src.settings.conf import amosettings, chatsettings, log
from src.utils.redis_conn import redis_client


class AmoCRMClient:
    @staticmethod
    async def _request(
        path: str,
        params: Optional[str] = None,
        body: Optional[dict | list] = None,
        method: str = "POST",
        headers: Optional[dict] = None,
    ) -> Tuple[int, Optional[httpx.Response]]:
        """
        Выполняет асинхронный HTTP-запрос с помощью httpx.
        :param path: Полный URL запроса.
        :param params: Тип параметров ('params', 'json', 'content').
        :param body: Тело запроса.
        :param method: Метод запроса (GET, POST и т.п.).
        :param headers: Заголовки запроса.
        :return: Кортеж (HTTP-статус, объект ответа или None).
        """
        request_arg = {
            "url": path,
            "headers": headers,
            params: body,
        }
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await getattr(client, method.lower())(**request_arg)
                response.raise_for_status()
                return response.status_code, response
        except httpx.HTTPStatusError as e:
            log.error(f"[AmoCRM] HTTP error: {e.response.status_code}")
            log.error(f"Ответ AmoCRM: {e.response.text}")
        except json.JSONDecodeError as e:
            log.error(f"[AmoCRM] Некорректный JSON: {e}")
        return 500, None

    def __init__(self):
        """
        Инициализация клиента AmoCRM с основными настройками.
        """
        self.access_token = amosettings.TOKEN
        self.base_url = amosettings.BASE_URL
        self.secret = chatsettings.AMO_CHATS_SECRET
        self.channel_id = chatsettings.AMO_CHATS_CHANNEL_ID
        self.account_id = chatsettings.AMO_CHATS_ACCOUNT_ID
        self.scope_id = f"{self.channel_id}_{self.account_id}"
        self.chat_base_url = "https://amojo.amocrm.ru"
        self.real_conversation_id: Optional[str] = None
        self.headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    async def _request_chat_base_url(
        self,
        path: str,
        params: Optional[str] = None,
        body: Optional[dict | list] = None,
        method: str = "POST",
    ) -> Tuple[int, Optional[str]]:
        """
        Делает авторизованный запрос в чат AmoCRM с HMAC-подписью.
        """
        content_type = "application/json"
        date = format_datetime(datetime.utcnow())

        request_body = json.dumps(body or {}, separators=(",", ":"))
        checksum = hashlib.md5(request_body.encode()).hexdigest()
        str_to_sign = "\n".join([method, checksum, content_type, date, path])
        signature = hmac.new(
            self.secret.encode(), str_to_sign.encode(), hashlib.sha1
        ).hexdigest()

        headers = {
            "Date": date,
            "Content-Type": content_type,
            "Content-MD5": checksum.lower(),
            "X-Signature": signature.lower(),
        }
        return await AmoCRMClient._request(
            path=self.chat_base_url + path,
            params=params,
            body=body,
            method=method,
            headers=headers,
        )

    async def find_contact_by_phone(self, phone: str) -> Optional[int]:
        """
        Поиск контакта по указанному номеру телефона
        :param phone: номер телефона в строковом формате
        :return: id контакта, если он существует или ничего
        """
        url = f"{self.base_url}/api/v4/contacts?query={phone}"
        status, data = await AmoCRMClient._request(
            path=url, method="GET", headers=self.headers
        )
        if status != 500:
            contacts = data.json().get("_embedded", {}).get("contacts", [])
            return contacts[0]["id"] if contacts else None
        return None

    async def create_or_get_contact(self, phone: str) -> Optional[int]:
        """
        Создание нового контакта по номеру телефона, если его нет
        :param phone: номер телефона в строковом формате
        :return: в случае успешного запроса возвращает id созданного контакта
        """
        contact_id = await self.find_contact_by_phone(phone)
        if contact_id:
            return contact_id

        url = f"{self.base_url}/api/v4/contacts"
        data = [
            {
                "name": phone,
                "custom_fields_values": [
                    {
                        "field_code": "PHONE",
                        "values": [{"value": phone, "enum_code": "WORK"}],
                    }
                ],
            }
        ]
        status, data = await AmoCRMClient._request(
            path=url, params="json", body=data, headers=self.headers
        )
        if status != 500:
            return data.json().get("_embedded", {}).get("contacts", [{}])[0].get("id")
        return None

    async def create_lead(
        self, contact_id: int, source: str = "WhatsApp"
    ) -> Optional[int]:
        """
        Создание нового лида
        :param contact_id: id существующего контакта
        :param source: откуда поступила заявка
        :return: в случае успешного запроса возвращает id лида
        """
        url = f"{self.base_url}/api/v4/leads/complex"
        data = [
            {
                "name": f"Заявка из {source}",
                "_embedded": {"contacts": [{"id": contact_id}]},
            }
        ]
        status, data = await AmoCRMClient._request(
            path=url, params="json", body=data, headers=self.headers
        )
        if status != 500:
            return data.json()[0]["id"]
        return None

    async def get_contact_phone_by_lead(self, lead_id: int) -> Optional[str]:
        """
        Получение данных по лиду
        :param lead_id: id существующего лида
        :return: в случае успешного запроса возвращает даннные по лиду
        """
        lead_url = f"{self.base_url}/api/v4/leads/{lead_id}?with=contacts"
        lead_status, lead_data = await AmoCRMClient._request(
            path=lead_url, headers=self.headers, method="GET"
        )
        contacts = None

        if lead_status != 500:
            contacts = lead_data.json().get("_embedded", {}).get("contacts", [])

        if not contacts:
            return None

        contact_id = contacts[0]["id"]
        url = f"{self.base_url}/api/v4/contacts/{contact_id}"
        status, data = await AmoCRMClient._request(
            path=url, headers=self.headers, method="GET"
        )
        if status != 500:
            fields = data.json().get("custom_fields_values", [])
            for f in fields:
                if f.get("field_code") == "PHONE":
                    values = f.get("values", [])
                    if values:
                        return values[0].get("value")
        return None

    async def create_chat(self, user_phone: str, operator_phone: str) -> Optional[str]:
        """
        Создаёт чат между пользователем и оператором в AmoCRM.
        :param user_phone: номер телефона контакта в строковом формате
        :param operator_phone: номер телефона оператора в строковом формате
        :return: в случае успешного запроса возвращает название чата
        """
        url = f"/v2/origin/custom/{self.scope_id}/chats"
        body = {
            "conversation_id": f"whatsapp:{user_phone}:{operator_phone}",
            "title": f"Чат {user_phone} — оператор {operator_phone}",
            "user": {
                "id": f"{user_phone}:{operator_phone}",
                "name": f"{user_phone}:{operator_phone}",
                "avatar": "https://via.placeholder.com/150",
                "profile": {"phone": user_phone},
            },
        }
        status, data = await self._request_chat_base_url(
            path=url, params="content", body=body
        )
        if status != 500:
            return f"whatsapp:{user_phone}:{operator_phone}"
        return None

    async def send_message_as_client_initial(
        self,
        phone: str,
        text: str,
        timestamp: int,
        conversation_id: Optional[str],
        operator_phone: str,
    ) -> None:
        """
        Отправляет сообщение от имени клиента.
        :param phone: номер телефона контакта в строковом формате
        :param text: сообщение от клиента
        :param timestamp: время в секундах
        :param conversation_id: внутренний id
        :param operator_phone: номер телефона оператора в строковом формате
        """
        url = f"/v2/origin/custom/{self.scope_id}"
        sender_id = f"{phone}:{operator_phone}"
        msg_id = f"client_{phone}_{timestamp}"
        body = {
            "event_type": "new_message",
            "payload": {
                "timestamp": int(timestamp),
                "msec_timestamp": int(timestamp) * 1000,
                "msgid": msg_id,
                "conversation_id": conversation_id,
                "silent": False,
                "sender": {
                    "id": sender_id,
                    "name": f"{conversation_id}",
                    "profile": {"phone": phone},
                },
                "message": {"type": "text", "text": text},
            },
        }
        await self._request_chat_base_url(path=url, params="content", body=body)

    async def connect_channel(self) -> None:
        """
        Подключает кастомный канал AmoCRM.
        """
        url = f"/v2/origin/custom/{self.channel_id}/connect"
        body = {
            "account_id": self.account_id,
            "hook_api_version": "v2",
            "title": "InDevelopment",
        }
        await self._request_chat_base_url(path=url, params="content", body=body)

    async def ensure_chat_visible(
        self, phone: str, text: str, timestamp: int, operator_phone: str
    ) -> None:
        """
        Гарантирует, что чат с клиентом существует и видим оператору.
        :param phone: номер телефона контакта в строковом формате
        :param text: сообщение от клиента
        :param timestamp: время в секундах
        :param operator_phone: номер телефона оператора в строковом формате
        """
        try:
            contact_id = await self.create_or_get_contact(phone)
            if not contact_id:
                log.error(f"[AmoCRM] Не удалось создать контакт для {phone}")
                return

            key = f"client_operator:{phone}"
            stored_operator = await redis_client.get(key)
            if isinstance(stored_operator, bytes):
                stored_operator = stored_operator.decode()

            if stored_operator != operator_phone:
                chat_id = await self.create_chat(phone, operator_phone)
                if chat_id:
                    await redis_client.set_chat_id(phone, operator_phone, chat_id)
                    await redis_client.set(key, operator_phone)
                    self.real_conversation_id = chat_id
            else:
                chat_id = await redis_client.get_chat_id(phone, operator_phone)
                self.real_conversation_id = chat_id

            await self.send_message_as_client_initial(
                phone, text, timestamp, self.real_conversation_id, operator_phone
            )
            await self.connect_channel()

        except Exception as e:
            log.exception(f"[AmoCRM] Ошибка в ensure_chat_visible: {str(e)}")

    async def send_message_from_manager(self, data: dict) -> None:
        """
        Отправляет сообщение от имени менеджера в чат.
        :param data: данные для запроса
        """
        url = f"/v2/origin/custom/{chatsettings.AMO_CHATS_SCOPE_ID}"
        body = {
            "event_type": "new_message",
            "payload": {
                "timestamp": data["timestamp"],
                "msec_timestamp": int(data["timestamp"]) * 1000,
                "msgid": data["message_id"],
                "conversation_id": data["conversation_id"],
                "silent": False,
                "sender": {"ref_id": chatsettings.AMO_CHATS_SENDER_USER_AMOJO_ID},
                "receiver": {
                    "id": str(data["user_id"]),
                    "avatar": data["avatar_link"],
                    "name": data["name"],
                },
                "message": {
                    "type": "text",
                    "text": data["message_text"],
                },
            },
        }
        await self._request_chat_base_url(path=url, params="content", body=body)

    async def get_templates(
        self, page: int = 1, limit: int = 50
    ) -> Optional[list[dict]]:
        """
        Получает список шаблонов чатов.
        :param page: номер страницы
        :param limit: количество шаблонов на странице
        :return: в случае успешного запроса возвращает json шаблонов
        """
        url = f"{self.base_url}/api/v4/chats/templates"
        body = {"page": page, "limit": limit}
        status, data = await AmoCRMClient._request(
            path=url, method="GET", params="params", body=body, headers=self.headers
        )
        if status == 204 or not data:
            return []
        if data:
            return data.json().get("_embedded", {}).get("chat_templates", [])
        return None

    async def get_template_by_id(self, template_id: str) -> Optional[dict]:
        """
        Получает шаблон по его external_id.
        :param template_id: внешний id  шаблона (присваивается от id waba template)
        :return: в случае успешного запроса возвращает шаблон в формате словаря
        """
        url = f"{self.base_url}/api/v4/chats/templates"
        body = {"filter[external_id]": template_id}
        status, data = await AmoCRMClient._request(
            path=url, method="GET", params="params", body=body, headers=self.headers
        )
        if status == 204 or not data:
            return None
        if data:
            return data.json().get("_embedded", {}).get("chat_templates", [])
        return None

    async def add_template(self, template: dict) -> Optional[int]:
        """
        Добавляет шаблон в AmoCRM, если его ещё нет.
        :param template: данные нового шаблона
        :return: в случае успешного запроса возвращает id созданного шаблона из AMO
        """
        existing_template = await self.get_template_by_id(template.get("external_id"))
        if existing_template:
            return None

        url = f"{self.base_url}/api/v4/chats/templates"
        status, data = await AmoCRMClient._request(
            path=url, params="json", body=[template], headers=self.headers
        )
        if status != 500:
            create_template = data.json().get("_embedded", {}).get("chat_templates", [])
            if create_template:
                return create_template[0].get("id")
        return None
