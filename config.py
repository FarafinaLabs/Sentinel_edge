"""Module de configuration centrale pour Sentinel-Edge."""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Paramètres d'exécution et de détection."""

    # 0 pour webcam locale ou URL complète RTSP/HTTP (ex: "http://192.168.1.50:8080/video")
    VIDEO_SOURCE = os.getenv("VIDEO_SOURCE", "0")

    # Paramètres de résolution et fréquence d'images
    FRAME_WIDTH = int(os.getenv("FRAME_WIDTH", "640"))
    FRAME_HEIGHT = int(os.getenv("FRAME_HEIGHT", "480"))
    TARGET_FPS = int(os.getenv("TARGET_FPS", "25"))

    # Paramètres de reconnexion réseau (Wi-Fi instable, RTSP, IP Webcam)
    RECONNECT_INTERVAL = float(os.getenv("RECONNECT_INTERVAL", "2.0"))
    MAX_RECONNECT_ATTEMPTS = int(os.getenv("MAX_RECONNECT_ATTEMPTS", "15"))

    # Inversion miroir horizontal (pour webcam locale et smartphone IP Webcam)
    MIRROR_VIDEO = os.getenv("MIRROR_VIDEO", "true").lower() in ("true", "1", "yes")

    # Paramètres de détection d'intrusion
    CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.60"))
    TARGET_CLASS = 0  # 0 correspond à 'person' dans COCO
    PERSISTENCE_FRAMES = int(os.getenv("PERSISTENCE_FRAMES", "2"))
    ALERT_COOLDOWN = int(os.getenv("ALERT_COOLDOWN", "10"))  # Secondes

    # Modèle YOLOv8
    YOLO_MODEL_PATH = os.getenv("YOLO_MODEL_PATH", "yolov8n.pt")

    # Notifications Telegram
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

    # Serveur Web Dashboard
    WEB_HOST = os.getenv("WEB_HOST", "0.0.0.0")
    WEB_PORT = int(os.getenv("WEB_PORT", "5000"))
    WEB_DEBUG = os.getenv("WEB_DEBUG", "false").lower() in ("true", "1", "yes")

    # Chemins de stockage local
    CAPTURE_DIR = os.getenv("CAPTURE_DIR", "captures")
    DATABASE_PATH = os.getenv("DATABASE_PATH", "sentinel.db")
