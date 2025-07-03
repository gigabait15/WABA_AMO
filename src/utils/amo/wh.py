import urllib.parse
from typing import Optional

import httpx

from waba_api.src.settings.conf import amosettings, log

_cached_external_id_field_id: Optional[int] = None


async def get_field_id_by_name(field_name: str) -> int:
    """
    Получает ID поля контакта по имени. Если не найдено — создаёт его.
    """
    url = f"{amosettings.BASE_URL}/contacts/custom_fields"
    headers = amosettings.get_headers()

    async with httpx.AsyncClient(timeout=20) as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
        except Exception as e:
            log.error(f"[amoCRM] Не удалось получить список полей: {e}")
            raise

        fields = response.json().get('_embedded', {}).get('custom_fields', [])
        for field in fields:
            if field.get("name", "").strip().lower() == field_name.lower():
                log.info(f"[amoCRM] Найден field_id={field['id']} для поля '{field_name}'")
                return field["id"]

        # Поле не найдено — создаём
        log.warning(f"[amoCRM] Поле '{field_name}' не найдено. Пытаемся создать...")

        create_payload = [{
            "type": "text",
            "name": field_name,
            "sort": 10,
            "is_api_only": False
        }]
        try:
            create_response = await client.post(url, headers=headers, json=create_payload)
            create_response.raise_for_status()
            created = create_response.json().get("_embedded", {}).get("custom_fields", [])
            if created:
                log.info(f"[amoCRM] Поле '{field_name}' успешно создано с id={created[0]['id']}")
                return created[0]["id"]
        except Exception as e:
            log.error(f"[amoCRM] Ошибка при создании поля '{field_name}': {e}")
            raise

    raise ValueError(f"[amoCRM] Поле с именем '{field_name}' не найдено и не удалось создать.")


async def find_or_create_contact(external_user_id: str) -> int:
    global _cached_external_id_field_id

    if _cached_external_id_field_id is None:
        _cached_external_id_field_id = await get_field_id_by_name("EXTERNAL ID")

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(
            f"{amosettings.BASE_URL}/contacts",
            headers=amosettings.get_headers(),
            params={"query": external_user_id}
        )

        if response.status_code == 200:
            contacts = response.json().get("_embedded", {}).get("contacts", [])
            for contact in contacts:
                for field in contact.get("custom_fields_values", []):
                    if field.get("field_id") == _cached_external_id_field_id:
                        for val in field.get("values", []):
                            if str(val.get("value")) == external_user_id:
                                log.info(f"[amoCRM] Найден контакт {contact['id']} по external_user_id={external_user_id}")
                                return contact["id"]

        # Контакт не найден — создаём
        payload = [{
            "name": f"User {external_user_id}",
            "custom_fields_values": [{
                "field_id": _cached_external_id_field_id,
                "values": [{"value": external_user_id}]
            }]
        }]

        response = await client.post(
            f"{amosettings.BASE_URL}/contacts",
            headers=amosettings.get_headers(),
            json=payload
        )
        response.raise_for_status()
        return response.json()["_embedded"]["contacts"][0]["id"]


async def get_default_pipeline_id_and_status_id() -> tuple[int, int]:
    """
    Возвращает pipeline_id и ID статуса с названием 'Новая заявка'
    из основной воронки (is_main = True).
    """
    url = f"{amosettings.BASE_URL}/leads/pipelines"
    headers = amosettings.get_headers()

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()

        pipelines = response.json().get('_embedded', {}).get('pipelines', [])
        if not pipelines:
            raise Exception("В amoCRM нет доступных воронок")

        main_pipeline = next((p for p in pipelines if p.get("is_main")), None)
        if not main_pipeline:
            raise Exception("В amoCRM не найдена основная воронка")

        pipeline_id = main_pipeline["id"]
        statuses = main_pipeline.get('_embedded', {}).get('statuses', [])
        if not statuses:
            raise Exception(f"У воронки {pipeline_id} нет статусов")

        for status in statuses:
            if status["name"].lower() == "новая заявка":
                log.debug(f"[amoCRM] Используем статус '{status['name']}' (id={status['id']}) из воронки {pipeline_id}")
                return pipeline_id, status["id"]

        raise Exception(f"Не найден статус 'Новая заявка' в воронке {pipeline_id}")


async def create_or_attach_lead_for_contact(contact_id: int) -> int:
    """
    Находит активную сделку для контакта или создаёт новую.
    """
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(
            f"{amosettings.BASE_URL}/leads",
            headers=amosettings.get_headers(),
            params={"filter[contacts][]": contact_id, "with": "contacts"}
        )
        response.raise_for_status()

        for lead in response.json().get("_embedded", {}).get("leads", []):
            contact_ids = [c["id"] for c in lead.get("_embedded", {}).get("contacts", [])]
            if contact_id in contact_ids and lead["status_id"] not in amosettings.CLOSED_STATUSES:
                log.info(f"Найдена активная сделка {lead['id']} для контакта {contact_id}")
                return lead["id"]

        pipeline_id, status_id = await get_default_pipeline_id_and_status_id()
        payload = [{
            "name": f"Диалог с контактом {contact_id}",
            "pipeline_id": pipeline_id,
            "status_id": status_id,
            "_embedded": {"contacts": [{"id": contact_id}]}
        }]
        response = await client.post(
            f"{amosettings.BASE_URL}/leads",
            headers=amosettings.get_headers(),
            json=payload
        )
        if response.status_code >= 400:
            log.error(f"[amoCRM] Ошибка создания сделки: {response.status_code}, {response.text}")
            response.raise_for_status()
        return response.json()["_embedded"]["leads"][0]["id"]


async def add_note(entity_type: str, entity_id: int, message: str) -> None:
    """
    Добавляет примечание к контакту или сделке.
    """
    try:
        note_payload = [{
            "note_type": "common",
            "params": {"text": message}
        }]
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"{amosettings.BASE_URL}/{entity_type}/{entity_id}/notes",
                headers=amosettings.get_headers(),
                json=note_payload
            )
            response.raise_for_status()
    except httpx.ConnectTimeout:
        log.error(f"[amoCRM] Таймаут при добавлении примечания в {entity_type} {entity_id}")


async def process_incoming_message(external_user_id: str, message: str) -> None:
    contact_id = await find_or_create_contact(external_user_id)
    lead_id = await create_or_attach_lead_for_contact(contact_id)
    await add_note("leads", lead_id, f"Входящее: {message}")


async def send_outgoing_message(external_user_id: str, message: str) -> bool:
    try:
        encoded_message = urllib.parse.quote(message)
        url = f"https://b517-103-175-213-92.ngrok-free.app/meta/send?wa_id={external_user_id}&text={encoded_message}"

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(url)

        if response.status_code == 200:
            contact_id = await find_or_create_contact(external_user_id)
            await add_note("contacts", contact_id, f"Исходящее: {message}")
            return True
        return False
    except Exception as e:
        log.exception(f"Ошибка в send_outgoing_message: {e}")
        return False


async def get_user_id_by_lead_id(lead_id: int) -> str:
    """
    Возвращает EXTERNAL ID (или телефон) по сделке.
    """
    global _cached_external_id_field_id
    if _cached_external_id_field_id is None:
        _cached_external_id_field_id = await get_field_id_by_name("EXTERNAL ID")

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(
            f"{amosettings.BASE_URL}/leads/{lead_id}",
            headers=amosettings.get_headers(),
            params={"with": "contacts"}
        )
        response.raise_for_status()

        contacts = response.json().get("_embedded", {}).get("contacts", [])
        if not contacts:
            raise Exception(f"У сделки {lead_id} нет контактов")

        for c in contacts:
            contact_id = c["id"]
            r = await client.get(f"{amosettings.BASE_URL}/contacts/{contact_id}", headers=amosettings.get_headers())
            r.raise_for_status()
            contact = r.json()

            for field in contact.get("custom_fields_values", []):
                if field.get("field_id") == _cached_external_id_field_id:
                    return str(field["values"][0]["value"])
                if field.get("field_name") == "Телефон":
                    return str(field["values"][0]["value"])

        raise Exception(f"Не найден EXTERNAL ID или Телефон для сделки {lead_id}")
