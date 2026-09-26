"""Pipeline d'orchestration principal de Sentinel-Edge.

Développé par AMADOU H TRAORE — Pôle Télécom, Réseau & Sécurité.
Connecte les modules du système en une boucle coordonnée :
    Stream (Thread 1) → Detector (Thread 2) → Notifier → Database

Ce module représente le cœur opérationnel du MVP : il lit les frames
du flux vidéo, les passe au détecteur YOLOv8, sauvegarde les snapshots
annotés en cas d'intrusion confirmée, envoie les alertes Telegram
de manière asynchrone et persiste les événements en base SQLite.
"""

import sys
import time
import logging
from pathlib import Path
from typing import Optional

import cv2

# Ajout de la racine au PYTHONPATH
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from config import Config
from core.stream import VideoStream
from core.database import SentinelDatabase

logger = logging.getLogger("Sentinel.Pipeline")


class SentinelPipeline:
    """Orchestrateur principal : Stream → Détection → Notification → BDD.

    Coordonne l'ensemble des composants du système en une boucle unique
    optimisée pour le Edge AI avec gestion du cooldown et de la persistance.

    Attributes:
        stream (VideoStream): Gestionnaire de flux vidéo.
        detector: Détecteur d'intrusion YOLOv8 (chargé à la demande).
        notifier: Notifieur Telegram (optionnel).
        database (SentinelDatabase): Base SQLite pour la persistance.
    """

    def __init__(self) -> None:
        """Initialise le pipeline avec tous les composants."""
        logger.info("Initialisation du pipeline Sentinel-Edge...")

        # Composant 1 : Flux vidéo (Thread 1 — Amadou)
        self.stream = VideoStream(
            source=Config.VIDEO_SOURCE,
            target_width=Config.FRAME_WIDTH,
            target_height=Config.FRAME_HEIGHT,
            target_fps=Config.TARGET_FPS,
            reconnect_interval=Config.RECONNECT_INTERVAL,
        )

        # Composant 2 : Détecteur YOLOv8 (Thread 2 — Tomota)
        self.detector = None
        self._load_detector()

        # Composant 3 : Notifieur Telegram (Pôle Télécom)
        self.notifier = None
        self._load_notifier()

        # Composant 4 : Base de données SQLite (Pôle Télécom)
        self.database = SentinelDatabase(db_path=Config.DATABASE_PATH)

        # État du pipeline
        self._running: bool = False
        self._total_intrusions: int = 0
        self._last_alert_time: float = 0.0

        logger.info("Pipeline Sentinel-Edge initialisé avec succès.")

    def _load_detector(self) -> None:
        """Charge le détecteur YOLOv8 de façon sécurisée."""
        try:
            from core.detector import IntrusionDetector

            self.detector = IntrusionDetector(
                model_name=Config.YOLO_MODEL_PATH,
                conf_thresh=Config.CONFIDENCE_THRESHOLD,
                persistence=Config.PERSISTENCE_FRAMES,
                device="cpu",
            )
            logger.info("Détecteur YOLOv8n chargé avec succès sur CPU.")
        except ImportError:
            logger.warning(
                "Module ultralytics non installé. "
                "Le pipeline fonctionne sans détection IA."
            )
        except Exception as e:
            logger.error(f"Erreur de chargement du détecteur : {e}")

    def _load_notifier(self) -> None:
        """Charge le notifieur Telegram si les tokens sont configurés."""
        try:
            from core.notifier import create_notifier_from_config

            self.notifier = create_notifier_from_config()
            if self.notifier:
                logger.info("Notifieur Telegram chargé et configuré.")
            else:
                logger.info("Telegram non configuré — alertes désactivées.")
        except Exception as e:
            logger.error(f"Erreur de chargement du notifieur : {e}")

    def _save_intrusion_snapshot(
        self, annotated_frame, confidence: float
    ) -> Optional[str]:
        """Sauvegarde un snapshot annoté avec bounding box et horodatage.

        Args:
            annotated_frame: Frame OpenCV annotée par le détecteur.
            confidence: Score de confiance maximal.

        Returns:
            str: Chemin du fichier sauvegardé, ou None.
        """
        capture_dir = Path(Config.CAPTURE_DIR)
        capture_dir.mkdir(parents=True, exist_ok=True)

        timestamp_str = time.strftime("%Y%m%d_%H%M%S")
        ms = int((time.time() % 1) * 1000)
        filename = f"intrusion_{timestamp_str}_{ms:03d}_conf{confidence:.0%}.jpg"
        filepath = capture_dir / filename

        # Ajout du bandeau horodaté officiel
        frame_copy = annotated_frame.copy()
        stamp = (
            f"SENTINEL-EDGE | INTRUSION DETECTEE | "
            f"{time.strftime('%Y-%m-%d %H:%M:%S')} | Conf: {confidence:.1%}"
        )
        h = frame_copy.shape[0]
        # Bandeau noir en bas
        cv2.rectangle(frame_copy, (0, h - 30), (frame_copy.shape[1], h), (0, 0, 0), -1)
        cv2.putText(
            frame_copy,
            stamp,
            (10, h - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (0, 255, 0),
            1,
            cv2.LINE_AA,
        )

        success = cv2.imwrite(str(filepath), frame_copy)
        if success:
            logger.info(f"Snapshot d'intrusion sauvegardé : {filepath}")
            return str(filepath)
        else:
            logger.error(f"Échec de la sauvegarde du snapshot : {filepath}")
            return None

    def run(self, display: bool = False) -> None:
        """Lance la boucle principale du pipeline.

        Args:
            display: Si True, affiche le flux vidéo annoté dans une fenêtre OpenCV.
                     Mettre à False en mode serveur/headless.
        """
        print("=" * 65)
        print("  🛡️  SENTINEL-EDGE — Pipeline de Surveillance (MVP V0)")
        print("  Auteur : AMADOU H TRAORE (Pôle IA & Télécom)")
        print(f"  Source : {Config.VIDEO_SOURCE}")
        print(f"  Détecteur : {'YOLOv8n actif' if self.detector else 'Désactivé'}")
        print(f"  Telegram : {'Configuré' if self.notifier else 'Non configuré'}")
        print(f"  Base SQLite : {Config.DATABASE_PATH}")
        print("=" * 65)

        self.stream.start()
        self._running = True

        try:
            while self._running:
                # Lecture de la dernière frame (zero-lag)
                success, frame = self.stream.read()
                if not success or frame is None:
                    time.sleep(0.05)
                    continue

                display_frame = frame

                # Inférence IA si le détecteur est chargé
                if self.detector:
                    is_confirmed, confidence, annotated = self.detector.process_frame(
                        frame
                    )
                    display_frame = annotated

                    # Intrusion confirmée !
                    if is_confirmed:
                        self._total_intrusions += 1
                        logger.warning(
                            f"🚨 INTRUSION CONFIRMÉE #{self._total_intrusions} "
                            f"(confiance={confidence:.2f})"
                        )

                        # Sauvegarde du snapshot
                        snapshot_path = self._save_intrusion_snapshot(
                            annotated, confidence
                        )

                        # Envoi Telegram asynchrone
                        telegram_sent = False
                        if self.notifier and snapshot_path:
                            self.notifier.send_alert_async(
                                image_path=snapshot_path,
                                confidence=confidence,
                            )
                            telegram_sent = True

                        # Persistance en base SQLite
                        self.database.log_intrusion(
                            confidence=confidence,
                            image_path=snapshot_path,
                            source=str(Config.VIDEO_SOURCE),
                            telegram_sent=telegram_sent,
                        )

                # Affichage optionnel (mode développement)
                if display:
                    cv2.imshow("Sentinel-Edge Pipeline", display_frame)
                    key = cv2.waitKey(1) & 0xFF
                    if key in (ord("q"), ord("Q"), 27):
                        logger.info("Arrêt demandé par l'utilisateur (touche Q).")
                        break

                # Throttle léger pour ne pas surcharger le CPU
                time.sleep(0.01)

        except KeyboardInterrupt:
            logger.info("Arrêt demandé par l'utilisateur (Ctrl+C).")
        finally:
            self.stop()

    def stop(self) -> None:
        """Arrête proprement tous les composants du pipeline."""
        self._running = False
        self.stream.stop()
        if cv2.getWindowProperty("Sentinel-Edge Pipeline", cv2.WND_PROP_VISIBLE) >= 0:
            cv2.destroyAllWindows()
        logger.info(
            f"Pipeline arrêté. Total intrusions détectées : {self._total_intrusions}"
        )


# =====================================================================
# Point d'entrée standalone
# =====================================================================
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    # Argument optionnel : --display pour afficher la fenêtre OpenCV
    show_display = "--display" in sys.argv

    pipeline = SentinelPipeline()
    pipeline.run(display=show_display)
