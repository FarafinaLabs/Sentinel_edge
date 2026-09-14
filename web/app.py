"""Application Web Dashboard pour le module d'ingestion vidéo Sentinel-Edge.

Développé par AMADOU H TRAORE — Binôme IA & Data.
Fournit :
- Interface Web moderne et réactive (Dark theme / Glassmorphism)
- Streaming vidéo MJPEG haute performance et faible latence
- Contrôle en direct des sources (Webcam PC, Smartphone IP Webcam, RTSP, Mock)
- Télémétrie en temps réel (FPS, drops, latence, statut)
- Déclencheur de snapshot instantané avec galerie
- Prévisualisation optionnelle du détecteur d'humains YOLOv8n
"""

import os
import sys
import time
import logging
from pathlib import Path
from typing import Generator
import cv2
import numpy as np
from flask import Flask, render_template, Response, jsonify, request, send_from_directory

# Ajout du dossier racine au sys.path pour les imports
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from config import Config
from core.stream import VideoStream, VideoStreamState

# Configuration des logs
logger = logging.getLogger("Sentinel.WebDashboard")

app = Flask(
    __name__,
    template_folder=str(ROOT_DIR / "web" / "templates"),
    static_folder=str(ROOT_DIR / "web" / "static"),
)

# Instance globale du flux vidéo
stream_manager = VideoStream(
    source=Config.VIDEO_SOURCE,
    target_width=Config.FRAME_WIDTH,
    target_height=Config.FRAME_HEIGHT,
    target_fps=Config.TARGET_FPS,
    reconnect_interval=Config.RECONNECT_INTERVAL,
)
stream_manager.start()

# Détecteur optionnel (chargé à la demande pour économiser les ressources)
ai_detector = None
ai_enabled = False
recent_logs = []


def log_event(msg: str, level: str = "INFO"):
    """Ajoute un log horodaté dans la file d'événements pour le dashboard."""
    timestamp = time.strftime("%H:%M:%S")
    entry = {"time": timestamp, "message": msg, "level": level}
    recent_logs.append(entry)
    if len(recent_logs) > 50:
        recent_logs.pop(0)


log_event("Initialisation du serveur Sentinel-Edge Web Dashboard...")
log_event(f"Source vidéo par défaut configurée : {Config.VIDEO_SOURCE}")


def get_or_load_detector():
    """Charge le détecteur YOLOv8 de façon paresseuse (lazy loading)."""
    global ai_detector
    if ai_detector is None:
        try:
            from core.detector import IntrusionDetector
            log_event("Chargement du modèle YOLOv8n...", "INFO")
            ai_detector = IntrusionDetector(
                model_name=Config.YOLO_MODEL_PATH,
                conf_thresh=Config.CONFIDENCE_THRESHOLD,
                persistence=2,
                device="cpu",
            )
            log_event("Modèle YOLOv8n chargé avec succès sur CPU.", "SUCCESS")
        except Exception as e:
            log_event(f"Erreur chargement YOLOv8 : {e}", "ERROR")
            ai_detector = None
    return ai_detector


def generate_frames() -> Generator[bytes, None, None]:
    """Générateur de flux MJPEG avec encodage JPEG optimisé."""
    global ai_enabled
    while True:
        success, frame = stream_manager.read()
        if not success or frame is None:
            # Si pas de frame disponible, générer une frame d'attente
            placeholder = np.zeros((360, 640, 3), dtype=np.uint8)
            cv2.putText(
                placeholder,
                "EN ATTENTE DU FLUX VIDEO...",
                (120, 180),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 165, 255),
                2,
            )
            ret, buffer = cv2.imencode(".jpg", placeholder)
            frame_bytes = buffer.tobytes()
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
            )
            time.sleep(0.1)
            continue

        display_frame = frame

        # Inférence IA si activée
        if ai_enabled:
            detector = get_or_load_detector()
            if detector:
                try:
                    _, _, display_frame = detector.process_frame(display_frame)
                except Exception as e:
                    pass

        # Encodage JPEG basse compression pour rapidité de streaming
        ret, buffer = cv2.imencode(
            ".jpg", display_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 75]
        )
        if not ret:
            time.sleep(0.02)
            continue

        frame_bytes = buffer.tobytes()
        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
        )
        time.sleep(0.01)


@app.route("/")
def index():
    """Page d'accueil du tableau de bord de surveillance."""
    return render_template("index.html")


@app.route("/video_feed")
def video_feed():
    """Endpoint de streaming vidéo MJPEG."""
    return Response(
        generate_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


@app.route("/api/status", methods=["GET"])
def api_status():
    """Retourne la télémétrie complète du flux en temps réel."""
    telemetry = stream_manager.get_telemetry()
    telemetry["ai_enabled"] = ai_enabled
    return jsonify(telemetry)


@app.route("/api/source", methods=["POST"])
def api_change_source():
    """Change la source vidéo à la volée."""
    data = request.get_json(silent=True) or {}
    new_src = data.get("source")
    if new_src is None or str(new_src).strip() == "":
        return jsonify({"success": False, "error": "Source vide ou invalide"}), 400

    new_src_clean = str(new_src).strip()
    log_event(f"Changement de source demandé : '{new_src_clean}'", "INFO")
    stream_manager.change_source(new_src_clean)
    return jsonify({"success": True, "source": new_src_clean})


@app.route("/api/snapshot", methods=["POST"])
def api_snapshot():
    """Déclenche la capture immédiate d'un snapshot."""
    capture_dir = Path(Config.CAPTURE_DIR)
    capture_dir.mkdir(parents=True, exist_ok=True)
    file_path = stream_manager.save_snapshot(output_dir=capture_dir)

    if file_path:
        filename = Path(file_path).name
        log_event(f"Snapshot enregistré : {filename}", "SUCCESS")
        return jsonify(
            {
                "success": True,
                "filename": filename,
                "path": file_path,
                "url": f"/captures/{filename}",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
    return jsonify({"success": False, "error": "Échec de la capture"}), 500


@app.route("/api/toggle_ai", methods=["POST"])
def api_toggle_ai():
    """Active ou désactive la détection YOLOv8 sur le flux."""
    global ai_enabled
    data = request.get_json(silent=True) or {}
    if "enabled" in data:
        ai_enabled = bool(data["enabled"])
    else:
        ai_enabled = not ai_enabled

    if ai_enabled:
        get_or_load_detector()
        log_event("Détecteur YOLOv8 activé sur le flux vidéo.", "WARNING")
    else:
        log_event("Détecteur YOLOv8 désactivé.", "INFO")

    return jsonify({"success": True, "ai_enabled": ai_enabled})


@app.route("/api/snapshots", methods=["GET"])
def api_list_snapshots():
    """Liste les 15 derniers clichés enregistrés."""
    capture_dir = Path(Config.CAPTURE_DIR)
    if not capture_dir.exists():
        return jsonify([])

    files = sorted(
        capture_dir.glob("*.jpg"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    result = [
        {
            "filename": f.name,
            "url": f"/captures/{f.name}",
            "size_kb": round(f.stat().st_size / 1024, 1),
            "created_at": time.strftime("%H:%M:%S", time.localtime(f.stat().st_mtime)),
        }
        for f in files[:15]
    ]
    return jsonify(result)


@app.route("/captures/<filename>")
def serve_capture(filename):
    """Sert une image capturée."""
    capture_dir = Path(Config.CAPTURE_DIR).resolve()
    return send_from_directory(str(capture_dir), filename)


@app.route("/api/logs", methods=["GET"])
def api_logs():
    """Retourne la file des derniers logs système."""
    return jsonify(recent_logs)


def start_server():
    """Lance le serveur web Flask."""
    print("=" * 65)
    print("  🚀 SENTINEL-EDGE — Web Dashboard d'Ingestion Vidéo")
    print(f"  Développé par AMADOU H TRAORE (Pôle IA & Data)")
    print(f"  URL locale : http://localhost:{Config.WEB_PORT}")
    print(f"  URL réseau : http://0.0.0.0:{Config.WEB_PORT}")
    print("=" * 65)
    app.run(
        host=Config.WEB_HOST,
        port=Config.WEB_PORT,
        debug=Config.WEB_DEBUG,
        threaded=True,
    )


if __name__ == "__main__":
    start_server()
