from typing import Optional

from redis.asyncio import Redis

from src.settings.conf import redissettings


class RedisClient:
    def __init__(self, url: str = None):
        if url is None:
            url = redissettings.redis_url
        self._redis = Redis.from_url(url, decode_responses=True)

    async def rpush(self, key: str, value: str) -> int:
        """Добавляет value в конец списка под ключом key. Возвращает новую длину списка."""
        return await self._redis.rpush(key, value)

    async def lpop(self, key: str) -> Optional[str]:
        """Извлекает и удаляет первый элемент списка под ключом key."""
        return await self._redis.lpop(key)

    async def set(self, key, value, ex=None):
        await self._redis.set(key, value)
        if ex:
            await self._redis.expire(key, ex)

    async def get(self, key: str) -> Optional[str]:
        val = await self._redis.get(key)
        return val

    async def get_chat_id(self, user_phone: str, operator_phone: str) -> Optional[str]:
        key = f"chat:{user_phone}:{operator_phone}"
        return await self._redis.get(key)

    async def set_chat_id(
            self, user_phone: str, operator_phone: str, chat_id: str, ttl: int = 86400
    ):
        key = f"chat:{user_phone}:{operator_phone}"
        await self._redis.set(key, chat_id, ex=ttl)

    async def close(self):
        await self._redis.close()


redis_client = RedisClient()
