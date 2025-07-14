import hashlib
import hmac
import json
from datetime import datetime
from email.utils import format_datetime
from typing import Optional, Tuple

import httpx
import requests

from src.settings.conf import amosettings, chatsettings, log
from src.utils.redis_conn import redis_client


class AmoCRMClient:
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

    def _auth_headers(self) -> dict:
        """
        Возвращает заголовки авторизации для API-запросов.
        """
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    def _find_contact_by_phone(self, phone: str) -> Optional[int]:
        """
        Ищет контакт в AmoCRM по номеру телефона.

        :param phone: Номер телефона для поиска.
        :return: ID найденного контакта или None.
        """
        try:
            url = f"{self.base_url}/api/v4/contacts?query={phone}"
            response = requests.get(url, headers=self._auth_headers())
            response.raise_for_status()
            data = response.json()
            contacts = data.get("_embedded", {}).get("contacts", [])
            return contacts[0]["id"] if contacts else None
        except requests.RequestException as e:
            log.error(f"[AmoCRM] Ошибка запроса при поиске контакта: {e}")
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            log.error(f"[AmoCRM] Ошибка парсинга ответа контакта: {e}")
            log.debug(f"Ответ: {response.text}")
        return None

    def create_or_get_contact(self, phone: str) -> Optional[int]:
        """
        Получает или создаёт контакт по номеру телефона.

        :param phone: Номер телефона.
        :return: ID контакта или None.
        """
        contact_id = self._find_contact_by_phone(phone)
        if contact_id:
            return contact_id
        try:
            url = f"{self.base_url}/api/v4/contacts"
            data = [{
                "name": phone,
                "custom_fields_values": [{
                    "field_code": "PHONE",
                    "values": [{"value": phone, "enum_code": "WORK"}],
                }]
            }]
            response = requests.post(url, headers=self._auth_headers(), json=data)
            response.raise_for_status()
            created = response.json()
            return created.get("_embedded", {}).get("contacts", [{}])[0].get("id")
        except requests.RequestException as e:
            log.error(f"[AmoCRM] Ошибка создания контакта: {e}")
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            log.error(f"[AmoCRM] Ошибка парсинга при создании контакта: {e}")
            log.debug(f"Ответ: {response.text}")
        return None

    def create_lead(self, contact_id: int, source: str = "WhatsApp") -> Optional[int]:
        """
        Создаёт сделку (лид), связанную с контактом.

        :param contact_id: ID контакта.
        :param source: Источник заявки.
        :return: ID сделки или None.
        """
        try:
            url = f"{self.base_url}/api/v4/leads/complex"
            data = [{
                "name": f"Заявка из {source}",
                "_embedded": {"contacts": [{"id": contact_id}]}
            }]
            response = requests.post(url, headers=self._auth_headers(), json=data)
            response.raise_for_status()
            return response.json()[0]["id"]
        except requests.RequestException as e:
            log.error(f"[AmoCRM] Ошибка создания сделки: {e}")
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            log.error(f"[AmoCRM] Ошибка парсинга ответа сделки: {e}")
            log.debug(f"Ответ: {response.text}")
        return None

    def get_contact_phone_by_lead(self, lead_id: int) -> Optional[str]:
        """
        Получает номер телефона контакта, связанного со сделкой.

        :param lead_id: ID сделки.
        :return: Номер телефона или None.
        """
        try:
            lead_url = f"{self.base_url}/api/v4/leads/{lead_id}?with=contacts"
            lead_resp = requests.get(lead_url, headers=self._auth_headers())
            lead_resp.raise_for_status()
            contacts = lead_resp.json().get("_embedded", {}).get("contacts", [])
            if not contacts:
                return None
            contact_id = contacts[0]["id"]
            contact_url = f"{self.base_url}/api/v4/contacts/{contact_id}"
            contact_resp = requests.get(contact_url, headers=self._auth_headers())
            contact_resp.raise_for_status()
            fields = contact_resp.json().get("custom_fields_values", [])
            for f in fields:
                if f.get("field_code") == "PHONE":
                    values = f.get("values", [])
                    if values:
                        return values[0].get("value")
        except requests.RequestException as e:
            log.error(f"[AmoCRM] Ошибка получения контакта по сделке {lead_id}: {e}")
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            log.error(f"[AmoCRM] Ошибка парсинга контакта по сделке: {e}")
        return None

    async def _post_to_amocrm(self, path: str, body: dict) -> Tuple[int, Optional[str]]:
        """
        Асинхронная отправка POST-запроса в AmoCRM чат-интеграцию.

        :param path: Путь запроса.
        :param body: Тело запроса.
        :return: Кортеж (HTTP статус, текст ответа).
        """
        try:
            method = "POST"
            content_type = "application/json"
            date = format_datetime(datetime.utcnow())
            request_body = json.dumps(body)
            checksum = hashlib.md5(request_body.encode()).hexdigest()
            str_to_sign = "\n".join([method, checksum, content_type, date, path])
            signature = hmac.new(self.secret.encode(), str_to_sign.encode(), hashlib.sha1).hexdigest()

            headers = {
                "Date": date,
                "Content-Type": content_type,
                "Content-MD5": checksum.lower(),
                "X-Signature": signature.lower(),
            }

            url = self.chat_base_url + path
            async with httpx.AsyncClient(timeout=30.0) as client:
                log.info(f"Request body:\n{request_body}")
                response = await client.post(url, headers=headers, data=request_body)

            log.info(f"POST {path} -> {response.status_code}")
            try:
                log.info(f"Response JSON: {response.json()}")
            except json.JSONDecodeError:
                log.warning(f"Некорректный JSON-ответ: {response.text}")
            return response.status_code, response.text
        except Exception as e:
            log.exception(f"[AmoCRM] Ошибка при POST {path}: {e}")
            return 500, None

    async def create_chat(self, user_phone: str, operator_phone: str) -> Optional[str]:
        """
        Создаёт чат для клиента и конкретного оператора.
        :param user_phone: Телефон клиента.
        :param operator_phone: Телефон оператора.
        :return: ID созданного чата или None.
        """
        path = f"/v2/origin/custom/{self.scope_id}/chats"
        conversation_id = f"whatsapp:{user_phone}:{operator_phone}"
        user_id = f"{user_phone}:{operator_phone}"
        body = {
            "conversation_id": conversation_id,
            "title": f"Чат {user_phone} — оператор {operator_phone}",
            "user": {
                "id": user_id,
                "name": user_id,
                "avatar": "https://via.placeholder.com/150",
                "profile": {"phone": user_phone},
            },
        }
        status, response_text = await self._post_to_amocrm(path, body)
        if status == 200:
            try:
                log.info(f"[AMO] conversation ID: {conversation_id}")
                return conversation_id

            except (json.JSONDecodeError, KeyError):
                log.warning("Не удалось извлечь chat ID из ответа.")
        return None

    async def send_message_as_client_initial(self, phone: str, text: str, timestamp: int,
                                             conversation_id: Optional[str], operator_phone: str):
        sender_id = f"{phone}:{operator_phone}"
        log.info(f"[AMO] send message client :{conversation_id}")
        msg_id = f"client_{phone}_{timestamp}"
        path = f"/v2/origin/custom/{self.scope_id}"
        payload = {
            "event_type": "new_message",
            "payload": {
                "timestamp": int(timestamp),
                "msec_timestamp": int(timestamp) * 1000,
                "msgid": msg_id,
                "conversation_id": conversation_id,
                "silent": False,
                "sender": {
                    "id": sender_id,
                    "name": f'{conversation_id}',
                    "profile": {"phone": phone},
                },
                "message": {
                    "type": "text",
                    "text": text
                },
            },
        }
        await self._post_to_amocrm(path, body=payload)

    async def connect_channel(self):
        """
        Подключает кастомный канал в AmoCRM.
        """
        url = f"/v2/origin/custom/{self.channel_id}/connect"
        payload = {
            "account_id": self.account_id,
            "hook_api_version": "v2",
            "title": "InDevelopment",
        }
        status, resp = await self._post_to_amocrm(url, payload)
        log.info(f"Подключение канала: статус={status}, ответ={resp}")

    async def ensure_chat_visible(self, phone: str, text: str, timestamp: int, operator_phone: str):
        try:
            # 1. Найти или создать контакт
            contact_id = self.create_or_get_contact(phone)
            if not contact_id:
                log.error(f"[AmoCRM] Не удалось создать контакт для {phone}")
                return

            key = f"client_operator:{phone}"
            stored_operator = await redis_client.get(key)
            if isinstance(stored_operator, bytes):
                stored_operator = stored_operator.decode()

            if stored_operator != operator_phone:
                log.info(f"[AmoCRM] Новый оператор для клиента {phone}. Был: {stored_operator}, стал: {operator_phone}")

                chat_id = await self.create_chat(phone, operator_phone)
                if chat_id:
                    await redis_client.set_chat_id(phone, operator_phone, chat_id)
                    await redis_client.set(key, operator_phone)
                    self.real_conversation_id = chat_id
            else:
                log.info(f"[AmoCRM] Оператор не изменился, используем текущий чат")
                chat_id = await redis_client.get_chat_id(phone, operator_phone)
                self.real_conversation_id = chat_id

            await self.send_message_as_client_initial(phone, text, timestamp, self.real_conversation_id, stored_operator)

            await self.connect_channel()

        except Exception as e:
            log.exception(f"[AmoCRM] Ошибка в ensure_chat_visible: {str(e)}")

    async def send_message_from_manager(self, data: dict):
        """
        Отправляет сообщение от менеджера клиенту.

        :param data: Словарь с данными сообщения.
        """
        url = f"/v2/origin/custom/{chatsettings.AMO_CHATS_SCOPE_ID}"
        payload = {
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
        await self._post_to_amocrm(url, payload)
