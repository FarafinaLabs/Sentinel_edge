import os

import requests
from dotenv import load_dotenv


load_dotenv()

token = os.getenv("TELEGRAM_BOT_TOKEN")
chat_id = os.getenv("TELEGRAM_CHAT_ID")

if not token or not chat_id:
    raise RuntimeError(
        "TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID est absent du fichier .env."
    )

response = requests.post(
    f"https://api.telegram.org/bot{token}/sendMessage",
    data={
        "chat_id": chat_id,
        "text": "✅ Sentinel-Edge : test de notification Telegram réussi.",
    },
    timeout=10,
)

response.raise_for_status()

data = response.json()

if not data.get("ok"):
    raise RuntimeError(data)

print("✅ Message envoyé. Vérifie Telegram.")