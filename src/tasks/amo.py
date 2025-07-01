import httpx


async def send_to_amo(external_user_id: str, text: str, log):
    """
    Асинхронно отправляет входящее сообщение из WhatsApp в amoCRM.
    Вызывается в фоновом режиме (через BackgroundTasks) при получении нового текстового сообщения в webhook от
    Meta Cloud API. Осуществляет HTTP POST-запрос
    к эндпоинту amoCRM, который:
      - создаёт или находит контакт по external_user_id (WA ID),
      - создаёт сделку (если отсутствует),
      - добавляет сообщение как примечание к сделке.
    Args:
        external_user_id (str): Уникальный идентификатор пользователя WhatsApp (WA ID).
        text (str): Текст сообщения, которое пришло от пользователя.
    Logs:
        - Успешную отправку в amoCRM.
        - Ошибки сетевого уровня или ошибки валидации от amo.
    Raises:
        Ничего не выбрасывает — ошибки логируются и подавляются, чтобы не мешать основному потоку обработки.
    """
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                "https://b517-103-175-213-92.ngrok-free.app/amo/webhook/incoming-message",
                json={"external_user_id": external_user_id, "message": text}
            )
            response.raise_for_status()
            log.info(f"[Meta→Amo] Передано сообщение в amo для {external_user_id}")
    except Exception as e:
        log.error(f"[Meta→Amo] Ошибка при отправке сообщения в amo: {e}")
