import traceback
from typing import Callable, Optional
from contextlib import asynccontextmanager

import aio_pika
from aiormq import exceptions as aiormq_exceptions

from src.settings.conf import rmqsetting
from src.settings.logger_config import get_logger

log = get_logger(__name__)


class AsyncRabbitMQRepository:
    def __init__(self, use_default_exchange: bool = True, exchange_name: str = None):
        self.host = rmqsetting.RABBITMQ_HOST
        self.port = rmqsetting.RABBITMQ_PORT
        self.user = rmqsetting.RABBITMQ_USER
        self.password = rmqsetting.RABBITMQ_PASSWORD
        self.connection: Optional[aio_pika.RobustConnection] = None
        self.channel: Optional[aio_pika.Channel] = None
        self.use_default_exchange = use_default_exchange
        self.exchange = None
        self.exchange_name = exchange_name

    async def connect(self):
        """Устанавливает асинхронное соединение с RabbitMQ."""
        if self.connection is None or self.connection.is_closed:
            self.connection = await aio_pika.connect_robust(
                host=self.host, port=self.port, login=self.user, password=self.password
            )
        if self.channel is None or self.channel.is_closed:
            self.channel = await self.connection.channel()

    @asynccontextmanager
    async def get_connection(self):
        """Context manager для автоматического управления соединением."""
        await self.connect()
        try:
            yield self
        finally:
            pass


    async def declare_exchange(self, exch_name = None, con_type = aio_pika.ExchangeType.FANOUT):
        name = exch_name if exch_name is not None else self.exchange_name
        if self.use_default_exchange:
            self.exchange = self.channel.default_exchange
        else:
            self.exchange = await self.channel.declare_exchange(
                name=name,
                type=con_type,
                durable=True,
                auto_delete=True,
            )

    async def create_queue(self, queue_name: str) -> str:
        """Создает очередь с указанным именем."""
        if not self.channel or not self.connection:
            await self.connect()
        if not self.exchange:
            await self.declare_exchange()
        queue = await self.channel.declare_queue(queue_name, durable=True)
        if not self.use_default_exchange:
            await queue.bind(self.exchange)
        return queue_name

    async def send_message(self, queue_name: str, message: str):
        """Отправляет сообщение в указанную очередь."""
        async with self.get_connection():
            if not self.exchange:
                await self.declare_exchange()

            await self.exchange.publish(
                aio_pika.Message(body=message.encode()),
                routing_key=queue_name if self.use_default_exchange else "",
            )

    async def consume_messages(self, queue_name: str, callback: Callable[[str, str], None]):
        """Начинает прослушивание очереди с вызовом callback(chat_id, message_body)."""
        if not self.channel or not self.connection:
            await self.connect()
        if not self.exchange:
            await self.declare_exchange()
        queue = await self.channel.declare_queue(queue_name, durable=True)
        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                try:
                    async with message.process():
                        body = message.body.decode()
                        import json
                        data = json.loads(body)
                        chat_id = str(data.get("chat_id"))
                        if chat_id:
                            await callback(chat_id, body)
                except Exception:
                    log.error(f"[RMQ] {traceback.format_exc()}")

    async def delete_queue(self, queue_name: str):
        """Удаляет очередь с указанным именем."""
        if not self.channel or not self.connection:
            await self.connect()
        try:
            queue = await self.channel.get_queue(queue_name)
            await queue.delete(if_unused=False, if_empty=False)
        except aio_pika.exceptions.QueueNotFound:
            return

    async def queue_exists(self, queue_name: str) -> bool:
        """Проверяет существование очереди по имени."""
        if not self.channel or not self.connection:
            await self.connect()
        try:
            await self.channel.get_queue(queue_name)
            return True
        except aiormq_exceptions.ChannelNotFoundEntity:
            return False
        except Exception as e:
            log.error(f"[RMQ] {traceback.format_exc()}")
            return False

    async def exchange_exists(self, exchange_name: str) -> bool:
        """
        Проверяет, существует ли обменник с указанным именем.
        Возвращает True, если обменник существует, иначе False.
        """
        if not self.connection or self.connection.is_closed:
            await self.connect()

        try:
            await self.channel.declare_exchange(exchange_name, passive=True)
            return True
        except Exception as ex:
            if "NOT_FOUND" in str(ex):
                return False
            return False


    async def declare_chat_exchange(self):
        self.channel = await self.connection.channel()
        await self.channel.declare_exchange("chat_exchange", aio_pika.ExchangeType.DIRECT)


    async def publish_to_chat(self, chat_id: str, message: str):
        """Отправляет сообщение в чат через exchange."""
        async with self.get_connection():
            if not self.exchange:
                await self.declare_exchange("chat_exchange", aio_pika.ExchangeType.DIRECT)
            
            # Используем exchange для отправки сообщения
            await self.exchange.publish(
                aio_pika.Message(body=message.encode()),
                routing_key=chat_id,
            )

    async def close(self):
        """Закрывает соединение с RabbitMQ."""
        try:
            if self.connection and not self.connection.is_closed:
                await self.connection.close()
        except Exception:
            log.error(f"[RMQ] {traceback.format_exc()}")


# Глобальный экземпляр для переиспользования соединений
_rmq_instance: Optional[AsyncRabbitMQRepository] = None

def get_rmq_instance() -> AsyncRabbitMQRepository:
    """Возвращает singleton экземпляр AsyncRabbitMQRepository."""
    global _rmq_instance
    if _rmq_instance is None:
        _rmq_instance = AsyncRabbitMQRepository()
    return _rmq_instance


def get_rmq_dependency() -> AsyncRabbitMQRepository:
    """Dependency функция для FastAPI для получения экземпляра RabbitMQ."""
    return get_rmq_instance()


async def cleanup_rmq():
    """Очищает глобальный экземпляр RabbitMQ."""
    global _rmq_instance
    if _rmq_instance is not None:
        await _rmq_instance.close()
        _rmq_instance = None

async def callback_wrapper(chat_id: str, message_body: str):
        rmq = get_rmq_instance()
        await rmq.publish_to_chat(chat_id, message_body)