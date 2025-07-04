import asyncio
import hashlib
import hmac
import json
from datetime import datetime
from email.utils import format_datetime
from typing import Optional

import httpx
import requests

from src.settings.conf import amosettings, chatsettings, log
from src.utils.redis_conn import redis_client


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
            
            try:
                data = response.json()
                contacts = data.get("_embedded", {}).get("contacts", [])
                return contacts[0]["id"] if contacts else None
            except (json.JSONDecodeError, KeyError, IndexError) as e:
                log.error(f"[AmoCRM] Failed to parse contacts response: {e}")
                log.debug(f"Response text: {response.text}")
                return None
                
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
                "custom_fields_values": [{
                    "field_code": "PHONE",
                    "values": [{"value": phone, "enum_code": "WORK"}]
                }]
            }]
            response = requests.post(url, headers=self._auth_headers(), json=data)
            response.raise_for_status()
            
            try:
                data = response.json()
                contacts = data.get("_embedded", {}).get("contacts", [])
                return contacts[0]["id"] if contacts else None
            except (json.JSONDecodeError, KeyError, IndexError) as e:
                log.error(f"[AmoCRM] Failed to parse create contact response: {e}")
                log.debug(f"Response text: {response.text}")
                return None
                
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
            
            try:
                data = response.json()
                return data[0]["id"] if data else None
            except (json.JSONDecodeError, KeyError, IndexError) as e:
                log.error(f"[AmoCRM] Failed to parse create lead response: {e}")
                log.debug(f"Response text: {response.text}")
                return None
                
        except Exception as e:
            log.error(f"[AmoCRM] Failed to create lead: {e}")
            return None

    def get_contact_phone_by_lead(self, lead_id: int) -> Optional[str]:
        try:
            url = f"{self.base_url}/api/v4/leads/{lead_id}?with=contacts"
            response = requests.get(url, headers=self._auth_headers())
            response.raise_for_status()
            
            try:
                data = response.json()
                contacts = data.get("_embedded", {}).get("contacts", [])
                if not contacts:
                    return None
                    
                contact_id = contacts[0]["id"]
                url = f"{self.base_url}/api/v4/contacts/{contact_id}"
                response = requests.get(url, headers=self._auth_headers())
                response.raise_for_status()
                
                contact_data = response.json()
                fields = contact_data.get("custom_fields_values", [])
                for f in fields:
                    if f.get("field_code") == "PHONE":
                        values = f.get("values", [])
                        if values:
                            return values[0]["value"]
                return None
                
            except (json.JSONDecodeError, KeyError, IndexError) as e:
                log.error(f"[AmoCRM] Failed to parse contact phone response: {e}")
                log.debug(f"Response text: {response.text}")
                return None
                
        except Exception as e:
            log.error(f"[AmoCRM] Failed to fetch phone for lead {lead_id}: {e}")
            return None

    async def _post_to_amocrm(self, path: str, body: dict):
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
                "Content-MD5": checksum,
                "X-Signature": signature,
            }

            url = self.chat_base_url + path
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, headers=headers, data=request_body)

            # log.info(f"POST {path} -> {response.status_code}")
            # log.debug(f"Response: {response.text}")

            # log.error(f"[AmoCRM] Chat message failed: {response.status_code} | {response.text}")
            # log.debug(f"Response Text:\n{response.text}")
            log.info(f"POST {path} -> {response.status_code}")
            
            try:
                resp = response.json()
                log.info(f"Response JSON: {resp}")
            except json.JSONDecodeError as e:
                log.error(f"Failed to parse JSON response: {e}")
                log.info(f"Response Text: {response.text}")
                resp = None
            except Exception as e:
                log.error(f"Unexpected error parsing response: {e}")
                resp = None

            return response.status_code, response.text
        except Exception as e:
            log.exception(f"[AmoCRM] Exception during POST to {path}: {e}")
            return 500, None

    async def create_chat(self, user_phone: str, operator_phone: str) -> Optional[str]:
        path = f"/v2/origin/custom/{self.scope_id}/chats"
        conversation_id = f"whatsapp:{user_phone}"
        body = {
            "conversation_id": conversation_id,
            # "source": {"external_id": operator_phone},
            "user": {
                "id": user_phone,
                "name": user_phone,
                "avatar": "https://via.placeholder.com/150",
                "profile": {"phone": user_phone}
            }
        }
        status, response_text = await self._post_to_amocrm(path, body)
        if status == 200:
            try:
                return json.loads(response_text)["id"]
            except Exception:
                log.warning("Could not extract chat id")
        return None

    async def send_message_as_client_initial(self, phone: str, text: str, timestamp: int):
        path = f"/v2/origin/custom/{self.scope_id}"
        timestamp = int(datetime.now().timestamp())
        msg_id = f"client_{phone}_{timestamp}"
        payload = {
            "event_type": "new_message",
            "payload": {
                "timestamp": int(timestamp),
                "msec_timestamp": int(timestamp) * 1000,
                "msgid": msg_id,
                "conversation_id": f"whatsapp_{phone}",
                "silent": False,
                "sender": {
                    "id": phone,
                    "name": "Client1",
                },
                "message": {
                    "type": "text",
                    "text": text
                }
            }
        }
        await self._post_to_amocrm(path, payload)
        

    async def ensure_chat_visible(self, phone: str, text: str, timestamp: int, operator_phone: str):
        # contact_id = self.create_or_get_contact(phone)
        # if contact_id:
        #     self.create_lead(contact_id)

        # chat_id = await redis_client.get_chat_id(phone, operator_phone)
        # if not chat_id:
        #     chat_id = await self.create_chat(phone, operator_phone)
        #     if chat_id:
        #         await redis_client.set_chat_id(phone, operator_phone, chat_id)

        # self.real_conversation_id = chat_id
        # await self.send_message_from_manager({
        #     "timestamp": timestamp,
        #     "message_id": f"client_{phone}_{timestamp}",
        #     "conversation_id": f"whatsapp:{phone}",
        #     "user_id": phone,
        #     "avatar_link": "https://via.placeholder.com/150",
        #     "name": "Client",
        #     "message_text": text
        # })
        await self.send_message_as_client_initial(phone, text, timestamp)
        
    async def connect_channel(self):
        url = f'/v2/origin/custom/{chatsettings.AMO_CHATS_CHANNEL_ID}/connect'

        resp = await self._post_to_amocrm(url, {
            "account_id": chatsettings.AMO_CHATS_ACCOUNT_ID,
            "hook_api_version": "v2",
            "title": "InDevelopment"
        })


    async def send_message_from_manager(self, data):
        url = f'/v2/origin/custom/{chatsettings.AMO_CHATS_SCOPE_ID}'
        data = {
            "event_type": "new_message",
            "payload": {
                "timestamp": data["timestamp"],
                "msec_timestamp": data["timestamp"] * 1000,
                "msgid": data['message_id'],
                "conversation_id": data["conversation_id"],
                "silent": False,
                "sender": {
                    "ref_id": chatsettings.AMO_CHATS_SENDER_USER_AMOJO_ID,
                },
                "receiver": {
                    "id": str(data['user_id']),
                    "avatar": data['avatar_link'],
                    "name": data['name']
                },
                "message": {
                    "type": "text",
                    "text": data['message_text'],
                }
            }
        }
        r = await self._post_to_amocrm(url, data)