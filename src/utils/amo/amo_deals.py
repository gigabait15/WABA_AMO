import httpx

from waba_api.src.database.DAO.crud import LeadBindingDAO
from waba_api.src.settings.conf import amosettings, log


async def get_or_create_contact(user_number: str|int) -> int | None:
    search_url = f"https://{amosettings.SUBDOMAIN}.amocrm.ru/api/v4/contacts"
    headers = {
        "Authorization": f"Bearer {amosettings.TOKEN}",
        "Content-Type": "application/json"
    }
    # Попробуем найти контакт по телефону
    params = {"query": user_number}
    async with httpx.AsyncClient() as client:
        resp = await client.get(search_url, headers=headers, params=params)

    if resp.status_code == 200:
        result = resp.json()
        if result["_embedded"]["contacts"]:
            return result["_embedded"]["contacts"][0]["id"]

    # Если не найден – создадим
    create_url = search_url
    data = [{
        "name": f"Клиент {user_number}",
        "custom_fields_values": [
            {
                "field_code": "PHONE",
                "values": [{"value": user_number, "enum_code": "WORK"}]
            }
        ]
    }]
    async with httpx.AsyncClient() as client:
        resp = await client.post(create_url, headers=headers, json=data)

    if resp.status_code in (200, 201):
        result = resp.json()
        return result["_embedded"]["contacts"][0]["id"]

    log.error(f"Не удалось создать контакт: {resp.text}")
    return None


async def create_lead_for_chat(user_number: str, operator_number: str)  :
    # Проверка в БД
    existing_lead = await LeadBindingDAO.get_lead(int(user_number), int(operator_number))
    if existing_lead:
        return existing_lead

    # 1. Получить или создать контакт
    contact_id = await get_or_create_contact(user_number)
    if not contact_id:
        return None

    # 2. Создать сделку
    data = [{
        "name": f"Чат с {user_number} на номер {operator_number}",
        "_embedded": {"contacts": [{"id": int(contact_id)}]}
    }]

    url = f"https://{amosettings.SUBDOMAIN}.amocrm.ru/api/v4/leads"
    headers = {"Authorization": f"Bearer {amosettings.TOKEN}", "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(url, headers=headers, json=data)
        if response.status_code in (200, 201):
            lead_id = response.json()["_embedded"]["leads"][0]["id"]
            await LeadBindingDAO.add_binding(int(user_number), int(operator_number), lead_id)
            return lead_id

    log.error(f"Ошибка создания сделки: {response.text}")
    return None