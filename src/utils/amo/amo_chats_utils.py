import datetime
import hashlib
import hmac
import json

import aiohttp

from waba_api.src.settings.conf import chatsettings as config
from waba_api.src.settings.conf import log


class AmoChats:
    log.info(f"[AMO API] Sender REF_ID used: {config.AMO_CHATS_SENDER_USER_AMOJO_ID}")

    def __init__(self):
        self.root = "https://amojo.amocrm.ru"
        self.secret = config.AMO_CHATS_SECRET
        self.scope_id = config.AMO_CHATS_SCOPE_ID
        self.account_id = config.AMO_CHATS_ACCOUNT_ID

    async def post(self, url, data=None):
        payload = json.dumps(data) if data else None
        log.info(f"[AMO API] Final payload: {payload}")
        return await self._send_request("post", url, data=payload)

    async def _send_request(self, method: str, url: str, data=None, params=None):
        content_type = "application/json"
        date_ = datetime.datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S +0000")
        check_sum = hashlib.md5(data.encode() if data else b"").hexdigest()
        str_to_sign = "\n".join([
            method.upper(),
            check_sum,
            content_type,
            date_,
            url.split("?")[0]
        ])
        signature = hmac.new(self.secret.encode(), str_to_sign.encode(), hashlib.sha1).hexdigest()

        headers = {
            "Date": date_,
            "Content-Type": content_type,
            "Content-MD5": check_sum.lower(),
            "X-Signature": signature.lower(),
        }

        full_url = self.root + url
        return await self._make_request(method.upper(), full_url, headers=headers, data=data)

    async def _make_request(self, method, url, headers=None, data=None):
        async with aiohttp.ClientSession() as session:
            async with session.request(method, url, headers=headers, data=data) as response:
                text = await response.text()
                if response.status in (200, 201):
                    log.debug(f"[AMO API] OK: {text}")
                    return await response.json()
                log.warning(f"[AMO API] Ошибка: {response.status} — {text}")
                return None

    async def register_client(self, ref_id: str, name: str, avatar: str = ""):
        url = f"/v2/origin/custom/{self.scope_id}"
        payload = {
            "event_type": "new_user",
            "payload": {
                "ref_id": str(ref_id),
                "name": name,
                "avatar": avatar
            }
        }
        log.info(f"[AMO API] Register client payload: {payload}")
        await self.post(url, payload)

    async def send_message_from_client(self, data: dict):
        """
        Отправка сообщения от клиента в amoCRM (инициирует чат).
        """
        url = f"/v2/origin/custom/{self.scope_id}"
        payload = {
            "event_type": "new_message",
            "payload": {
                "timestamp": data["timestamp"],
                "msec_timestamp": data["timestamp"] * 1000,
                "msgid": data["message_id"],
                "conversation_id": str(data["conversation_id"]),
                "silent": False,
                "sender": {
                    "id": str(data["user_id"]),
                    "avatar": data["avatar_link"],
                    "name": data["name"]
                },
                "receiver": {
                    "ref_id": config.AMO_CHATS_SENDER_USER_AMOJO_ID
                },
                "message": {
                    "type": "text",
                    "text": data["message_text"]
                }
            }
        }
        await self.post(url, payload)

    async def send_message_from_manager(self, data: dict):
        url = f'/v2/origin/custom/{config.AMO_CHATS_SCOPE_ID}'
        payload = {
            "event_type": "new_message",
            "payload": {
                "timestamp": data["timestamp"],
                "msec_timestamp": data["timestamp"] * 1000,
                "msgid": data['message_id'],
                "conversation_id": data["conversation_id"],
                "silent": False,
                "sender": {
                    "ref_id": "8e19c9c2-6452-4417-89a1-ddca2e238f92",
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

        log.info(f"[AMO API] Final payload (no receiver): {payload}")
        await self.post(url, payload)
