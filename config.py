"""Module de configuration centrale pour Sentinel-Edge."""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Paramètres d'exécution et de détection."""

    # 0 pour webcam locale ou URL complète RTSP/HTTP (ex: "http://192.168.1.50:8080/video")
    VIDEO_SOURCE = os.getenv("VIDEO_SOURCE", "0")

    # Paramètres de détection d'intrusion
    CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.60"))
    TARGET_CLASS = 0  # 0 correspond à 'person' dans COCO
    PERSISTENCE_FRAMES = 2  # Détections consécutives requises pour validation
    ALERT_COOLDOWN = int(os.getenv("ALERT_COOLDOWN", "10"))  # Secondes

    # Notifications Telegram
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

    # Chemins de stockage local
    CAPTURE_DIR = "captures"
    DATABASE_PATH = "sentinel.db"
