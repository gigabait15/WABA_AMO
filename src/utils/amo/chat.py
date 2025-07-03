import hashlib
import hmac
import json
from datetime import datetime
from email.utils import format_datetime
from typing import Optional

import httpx
import requests

from waba_api.src.settings.conf import amosettings, chatsettings, log


class AmoCRMClient:
    def __init__(self):
        self.access_token = amosettings.TOKEN
        self.base_url = amosettings.BASE_URL
        self.secret = chatsettings.AMO_CHATS_SECRET
        self.channel_id = chatsettings.AMO_CHATS_CHANNEL_ID
        self.account_id = chatsettings.AMO_CHATS_ACCOUNT_ID
        self.scope_id = f"{self.channel_id}_{self.account_id}"
        self.chat_base_url = "https://amojo.amocrm.ru"
        self.real_conversation_id = None

    def _auth_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

    def _find_contact_by_phone(self, phone: str) -> Optional[int]:
        try:
            url = f"{self.base_url}/api/v4/contacts?query={phone}"
            response = requests.get(url, headers=self._auth_headers())
            response.raise_for_status()
            contacts = response.json()["_embedded"]["contacts"]
            return contacts[0]["id"] if contacts else None
        except Exception as e:
            log.error(f"[AmoCRM] Contact search failed: {e}")
            return None

    def create_or_get_contact(self, phone: str) -> Optional[int]:
        contact_id = self._find_contact_by_phone(phone)
        if contact_id:
            return contact_id
        try:
            url = f"{self.base_url}/api/v4/contacts"
            data = [{
                "name": phone,
                "custom_fields_values": [
                    {
                        "field_code": "PHONE",
                        "values": [{"value": phone, "enum_code": "WORK"}]
                    }
                ]
            }]
            response = requests.post(url, headers=self._auth_headers(), json=data)
            response.raise_for_status()
            contact_id = response.json()["_embedded"]["contacts"][0]["id"]
            log.info(f"[AmoCRM] Created new contact: {contact_id}")
            return contact_id
        except Exception as e:
            log.error(f"[AmoCRM] Failed to create contact: {e}")
            return None

    def create_lead(self, contact_id: int, source: str = "WhatsApp") -> Optional[int]:
        try:
            url = f"{self.base_url}/api/v4/leads/complex"
            data = [{
                "name": f"Заявка из {source}",
                "_embedded": {
                    "contacts": [{"id": contact_id}]
                }
            }]
            response = requests.post(url, headers=self._auth_headers(), json=data)
            response.raise_for_status()
            lead_id = response.json()[0]["id"]
            log.info(f"[AmoCRM] Created lead: {lead_id}")
            return lead_id
        except Exception as e:
            log.error(f"[AmoCRM] Failed to create lead: {e}")
            return None

    async def _post_to_amocrm(self, path: str, body: dict):
        try:
            method = "POST"
            content_type = "application/json"
            date = format_datetime(datetime.utcnow())
            request_body = json.dumps(body)
            checksum = hashlib.md5(request_body.encode("utf-8")).hexdigest()
            str_to_sign = "\n".join([method, checksum, content_type, date, path])
            signature = hmac.new(self.secret.encode(), str_to_sign.encode(), hashlib.sha1).hexdigest()

            headers = {
                "Date": date,
                "Content-Type": content_type,
                "Content-MD5": checksum,
                "X-Signature": signature,
            }

            url = self.chat_base_url + path
            log.info("📤 Sending request to amoCRM Chat API")
            log.info(f"URL: {url}")
            log.info(f"Headers: {json.dumps(headers, indent=2)}")
            log.info(f"Body: {json.dumps(body, indent=2)}")

            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, headers=headers, data=request_body)

            log.info(f"📥 Response status: {resp.status_code}")
            log.info(f"📥 Response body: {resp.text}")

            if resp.status_code != 200:
                log.error(f"[AmoCRM] Chat message failed: {resp.status_code} | {resp.text}")

            return resp.status_code, resp.text
        except Exception as e:
            log.exception(f"[AmoCRM] Exception during chat message: {e}")
            return 500, None  # Fallback

    async def send_message_as_client_initial(self, phone: str, text: str, timestamp: int):
        msg_id = hashlib.md5(f"{phone}{timestamp}".encode()).hexdigest()
        path = f"/v2/origin/custom/{self.scope_id}"
        body = {
            "event_type": "new_message",
            "payload": {
                "timestamp": timestamp,
                "msgid": msg_id,
                "conversation_id": f"whatsapp:{phone}",
                "sender": {
                    "id": phone,
                    "name": phone,
                    "profile": f"https://wa.me/{phone}",
                    "avatar": 'avatar'
                },
                "message": {
                    "type": "text",
                    "text": text
                }
            }
        }
        return await self._post_to_amocrm(path, body)

    async def send_message_from_manager(self, phone: str, text: str, timestamp: int):
        msg_id = f"manager_{phone}_{timestamp}"
        path = f"/v2/origin/custom/{self.scope_id}"
        body = {
            "event_type": "new_message",
            "payload": {
                "timestamp": timestamp,
                "msec_timestamp": timestamp * 1000,
                "msgid": msg_id,
                "conversation_id": f"whatsapp:{phone}",
                "silent": False,
                "sender": {
                    "ref_id": chatsettings.AMO_CHATS_SENDER_USER_AMOJO_ID
                },
                "receiver": {
                    "id": phone,
                    "name": phone,
                    "avatar": 'avatar'
                },
                "message": {
                    "type": "text",
                    "text": text
                }
            }
        }
        status, response_text = await self._post_to_amocrm(path, body)
        if status == 200:
            try:
                response_data = json.loads(response_text)
                self.real_conversation_id = response_data.get("new_message", {}).get("conversation_id")
            except Exception:
                log.warning("Could not extract conversation_id from response")

    async def send_message_to_chat(self, rel_id: str, phone: str, text: str, timestamp: int):
        msg_id = hashlib.md5(f"{phone}{timestamp}".encode()).hexdigest()
        path = f"/v2/origin/custom/{self.scope_id}"
        body = {
            "event_type": "new_message",
            "payload": {
                "timestamp": timestamp,
                "msgid": msg_id,
                "conversation_id": f"whatsapp:{phone}", #rel_id,
                "sender": {
                    "id": phone,
                    "name": phone,
                    "profile": f"https://wa.me/{phone}",
                    "avatar": 'avatar'
                },
                "message": {
                    "type": "text",
                    "text": text
                }
            }
        }
        await self._post_to_amocrm(path, body)

    async def ensure_chat_visible(self, phone: str, text: str, timestamp: int):
        status, _ = await self.send_message_as_client_initial(phone, text, timestamp)
        if status == 404 or 400:
            log.warning("Client message failed — fallback to manager only")
            await self.send_message_from_manager(phone, text, timestamp)
            await self.send_message_to_chat(self.real_conversation_id, phone, text, timestamp)