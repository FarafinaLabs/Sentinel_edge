"""Application Web Dashboard pour le module d'ingestion vidéo Sentinel-Edge.

Développé par AMADOU H TRAORE — Binôme IA & Data + Pôle Télécom.
Fournit :
- Interface Web moderne et réactive (Dark theme / Glassmorphism)
- Streaming vidéo MJPEG haute performance et faible latence
- Contrôle en direct des sources (Webcam PC, Smartphone IP Webcam, RTSP, Mock)
- Télémétrie en temps réel (FPS, drops, latence, statut)
- Déclencheur de snapshot instantané avec galerie
- Prévisualisation optionnelle du détecteur d'humains YOLOv8n
- Historique des intrusions persisté en base SQLite
- Statistiques du module Telegram
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
from core.database import SentinelDatabase

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
    mirror_video=Config.MIRROR_VIDEO,
)
stream_manager.start()

# Base de données SQLite pour l'historique des intrusions
db = SentinelDatabase(db_path=Config.DATABASE_PATH)

# Détecteur optionnel (chargé à la demande pour économiser les ressources)
ai_detector = None
ai_enabled = False
recent_logs = []

# Notifieur Telegram (optionnel)
telegram_notifier = None


def log_event(msg: str, level: str = "INFO"):
    """Ajoute un log horodaté dans la file d'événements pour le dashboard."""
    timestamp = time.strftime("%H:%M:%S")
    entry = {"time": timestamp, "message": msg, "level": level}
    recent_logs.append(entry)
    if len(recent_logs) > 50:
        recent_logs.pop(0)


log_event("Initialisation du serveur Sentinel-Edge Web Dashboard...")
log_event(f"Source vidéo par défaut configurée : {Config.VIDEO_SOURCE}")
log_event(f"Base de données SQLite : {Config.DATABASE_PATH}")


def _init_telegram():
    """Initialise le notifieur Telegram si les tokens sont configurés."""
    global telegram_notifier
    try:
        from core.notifier import create_notifier_from_config
        telegram_notifier = create_notifier_from_config()
        if telegram_notifier:
            log_event("Module Telegram chargé et configuré.", "SUCCESS")
        else:
            log_event("Telegram non configuré (tokens manquants).", "WARNING")
    except Exception as e:
        log_event(f"Erreur chargement Telegram : {e}", "ERROR")


_init_telegram()


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
                persistence=Config.PERSISTENCE_FRAMES,
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
                    is_confirmed, confidence, display_frame = detector.process_frame(
                        display_frame
                    )

                    # Si intrusion confirmée, enregistrer et notifier
                    if is_confirmed:
                        _handle_intrusion(display_frame, confidence)

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


def _handle_intrusion(annotated_frame, confidence: float):
    """Gère une intrusion confirmée : snapshot, BDD, Telegram."""
    # Sauvegarde du snapshot annoté
    capture_dir = Path(Config.CAPTURE_DIR)
    capture_dir.mkdir(parents=True, exist_ok=True)

    timestamp_str = time.strftime("%Y%m%d_%H%M%S")
    ms = int((time.time() % 1) * 1000)
    filename = f"intrusion_{timestamp_str}_{ms:03d}.jpg"
    filepath = capture_dir / filename

    # Ajout du bandeau horodaté
    frame_copy = annotated_frame.copy()
    stamp = f"SENTINEL-EDGE | {time.strftime('%Y-%m-%d %H:%M:%S')} | Conf: {confidence:.1%}"
    h = frame_copy.shape[0]
    cv2.rectangle(frame_copy, (0, h - 28), (frame_copy.shape[1], h), (0, 0, 0), -1)
    cv2.putText(
        frame_copy, stamp, (10, h - 8),
        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1, cv2.LINE_AA,
    )
    cv2.imwrite(str(filepath), frame_copy)

    # Envoi Telegram asynchrone
    telegram_sent = False
    if telegram_notifier:
        telegram_notifier.send_alert_async(
            image_path=str(filepath),
            confidence=confidence,
        )
        telegram_sent = True

    # Persistance en base SQLite
    db.log_intrusion(
        confidence=confidence,
        image_path=str(filepath),
        source=str(Config.VIDEO_SOURCE),
        telegram_sent=telegram_sent,
    )

    log_event(
        f"🚨 Intrusion détectée ! Confiance: {confidence:.1%} — {filename}",
        "WARNING",
    )


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

    # Ajout des stats Telegram
    if telegram_notifier:
        telemetry["telegram"] = telegram_notifier.get_stats()
        telemetry["telegram_configured"] = True
    else:
        telemetry["telegram_configured"] = False

    # Ajout des stats BDD
    telemetry["db_stats"] = db.get_stats()

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


@app.route("/api/intrusions", methods=["GET"])
def api_intrusion_history():
    """Retourne l'historique des intrusions depuis la base SQLite."""
    limit = request.args.get("limit", 50, type=int)
    events = db.get_recent_events(limit=limit)
    return jsonify(events)


@app.route("/api/intrusions/stats", methods=["GET"])
def api_intrusion_stats():
    """Retourne les statistiques agrégées des intrusions."""
    stats = db.get_stats()
    return jsonify(stats)


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
    print(f"  Base SQLite : {Config.DATABASE_PATH}")
    print(f"  Telegram : {'Configuré ✅' if telegram_notifier else 'Non configuré ❌'}")
    print("=" * 65)
    app.run(
        host=Config.WEB_HOST,
        port=Config.WEB_PORT,
        debug=Config.WEB_DEBUG,
        threaded=True,
    )


if __name__ == "__main__":
    start_server()
