import requests

from src.settings.conf import metasettings

APP_ID = metasettings.APP_ID
APP_SECRET = "..."
CURRENT_TOKEN = metasettings.TOKEN

url = f"{metasettings.BASE_URL}/v19.0/oauth/access_token"
params = {
    "grant_type": "fb_exchange_token",
    "client_id": APP_ID,
    "client_secret": APP_SECRET,
    "fb_exchange_token": CURRENT_TOKEN,
}

response = requests.get(url, params=params)
data = response.json()

if "access_token" in data:
    print("✅ Новый токен:", data["access_token"])
    print("⏰ Истекает через (сек):", data["expires_in"])
else:
    print("❌ Ошибка:", data)
