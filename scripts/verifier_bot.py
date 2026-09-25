import os

import requests
from dotenv import load_dotenv

load_dotenv()

token = os.getenv("TELEGRAM_BOT_TOKEN")

if not token:
    raise RuntimeError(
        "TELEGRAM_BOT_TOKEN est absent du fichier .env."
    )

response = requests.get(
    f"https://api.telegram.org/bot{token}/getMe",
    timeout=10,
)

response.raise_for_status()

data = response.json()

if not data.get("ok"):
    raise RuntimeError(data)

bot = data["result"]

print("Bot Telegram vérifié avec succès.")
print(f"Nom : {bot['first_name']}")
print(f"Username : @{bot['username']}")
print(f"ID : {bot['id']}")