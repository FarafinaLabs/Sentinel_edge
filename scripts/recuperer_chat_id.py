import os
from pathlib import Path

import requests
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"

load_dotenv(ENV_FILE)

token = os.getenv("TELEGRAM_BOT_TOKEN")

if not token:
    raise RuntimeError(
        f"TELEGRAM_BOT_TOKEN est absent du fichier : {ENV_FILE}"
    )

url = f"https://api.telegram.org/bot{token}/getUpdates"

try:
    response = requests.get(url, timeout=10)
    response.raise_for_status()
except requests.RequestException as error:
    raise RuntimeError(
        f"Impossible de contacter l’API Telegram : {error}"
    ) from error

data = response.json()

if not data.get("ok"):
    raise RuntimeError(
        f"Telegram a retourné une erreur : {data}"
    )

updates = data.get("result", [])

if not updates:
    print("Aucune mise à jour reçue par le bot.")
    print("1. Ouvre @sentinel_edge_alert_bot dans Telegram.")
    print("2. Clique sur Démarrer.")
    print("3. Envoie un message : test Sentinel Edge")
    print("4. Relance ensuite ce script.")
else:
    found_chat = False

    print("\nChats détectés :\n")

    for update in updates:
        message = (
            update.get("message")
            or update.get("edited_message")
            or update.get("channel_post")
        )

        if not message:
            continue

        chat = message.get("chat", {})
        chat_id = chat.get("id")

        if chat_id is None:
            continue

        found_chat = True

        chat_type = chat.get("type", "inconnu")
        chat_name = (
            chat.get("title")
            or chat.get("first_name")
            or chat.get("username")
            or "Inconnu"
        )

        print(f"Chat ID : {chat_id}")
        print(f"Type    : {chat_type}")
        print(f"Nom     : {chat_name}")
        print("-" * 40)

    if not found_chat:
        print("Des mises à jour ont été reçues, mais aucun chat exploitable n’a été trouvé.")
        print("Envoie un message texte au bot puis relance le script.")