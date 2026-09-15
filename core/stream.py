"""Module d'ingestion vidéo multithreadé optimisé pour l'Edge AI (Sentinel-Edge).

Développé par AMADOU H TRAORE — Binôme IA & Data (Sentinel-Edge MVP V0).
Ce module implémente le Thread 1 de l'architecture logicielle :
- Acquisition vidéo asynchrone non-bloquante (Webcam locale, IP Webcam Android, RTSP, Mock).
- Buffer ultra-court avec stratégie 'Drop Oldest' (élimination du décalage/drift de latence).
- Reconnexion automatique avec reprise après déconnexion réseau (Wi-Fi instable).
- Métriques temps réel (FPS effectif, frames abandonnées, résolution, télémétrie).
"""

import os
import sys
import time
import logging
import threading
from typing import Optional, Tuple, Union, Dict, Any
from pathlib import Path
import numpy as np
import cv2

# Configuration des logs du module
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [VideoStream] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("Sentinel.VideoStream")


class VideoStreamState:
    """États du cycle de vie du flux vidéo."""
    INITIALIZING = "INITIALIZING"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    RECONNECTING = "RECONNECTING"
    DISCONNECTED = "DISCONNECTED"
    STOPPED = "STOPPED"
    ERROR = "ERROR"


class VideoStream:
    """Moteur d'acquisition vidéo asynchrone multithreadé (Thread 1).

    Lit continuellement les frames depuis la source vidéo dans un thread d'arrière-plan
    (daemon) et ne conserve en mémoire que la frame la plus récente ('drop oldest').
    Cela garantit un temps de réponse temps réel à latence quasi-nulle (0 ms de queue lag)
    pour les threads d'inférence IA et de monitoring.
    """

    def __init__(
        self,
        source: Union[int, str] = 0,
        target_width: int = 640,
        target_height: int = 480,
        target_fps: int = 30,
        reconnect_interval: float = 2.0,
        max_reconnect_attempts: int = 15,
    ) -> None:
        """Initialise le gestionnaire de flux vidéo.

        Args:
            source: 0/1 pour webcam, URL HTTP/RTSP (ex: "http://192.168.1.50:8080/video"),
                    nom de fichier vidéo, ou "mock" pour mire de test synthétique.
            target_width: Largeur de redimensionnement pour alléger l'inférence Edge.
            target_height: Hauteur de redimensionnement.
            target_fps: Fréquence cible souhaitée.
            reconnect_interval: Délai en secondes entre deux tentatives de reconnexion.
            max_reconnect_attempts: Nombre max de tentatives avant passage en état ERROR.
        """
        self.raw_source: Union[int, str] = source
        self.source = self._normalize_source(source)
        self.target_width: int = target_width
        self.target_height: int = target_height
        self.target_fps: int = target_fps
        self.reconnect_interval: float = reconnect_interval
        self.max_reconnect_attempts: int = max_reconnect_attempts

        # État interne et synchronisation thread-safe
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        # Capture OpenCV
        self._cap: Optional[cv2.VideoCapture] = None
        self._is_mock: bool = (str(self.source).lower() == "mock")

        # Données de la dernière frame
        self._latest_frame: Optional[np.ndarray] = None
        self._has_new_frame: bool = False
        self._last_frame_timestamp: float = 0.0

        # Télémétrie et métriques industrielles
        self._state: str = VideoStreamState.INITIALIZING
        self._total_frames_read: int = 0
        self._total_frames_dropped: int = 0
        self._fps_actual: float = 0.0
        self._reconnect_count: int = 0
        self._start_time: float = 0.0
        self._last_error: str = ""
        self._actual_resolution: Tuple[int, int] = (target_width, target_height)

        # Variables pour le simulateur synthétique (Mode Mock)
        self._mock_pos_x: int = 100
        self._mock_pos_y: int = 100
        self._mock_dir_x: int = 5
        self._mock_dir_y: int = 4

    @staticmethod
    def _normalize_source(src: Union[int, str]) -> Union[int, str]:
        """Normalise la source passée en paramètre (convertit les chaînes numériques en int)."""
        if isinstance(src, str):
            src_str = src.strip()
            if src_str.isdigit():
                return int(src_str)
            return src_str
        return src

    @property
    def state(self) -> str:
        """Retourne l'état actuel du flux."""
        with self._lock:
            return self._state

    @property
    def is_active(self) -> bool:
        """Indique si le thread de capture est en cours d'exécution."""
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> "VideoStream":
        """Démarre le thread d'acquisition vidéo en arrière-plan."""
        if self.is_active:
            logger.warning("Le thread VideoStream est déjà en cours d'exécution.")
            return self

        self._stop_event.clear()
        self._start_time = time.time()
        self._state = VideoStreamState.CONNECTING

        logger.info(f"Démarrage du flux vidéo sur la source : {self.source}")
        self._thread = threading.Thread(
            target=self._capture_loop,
            name="Sentinel-VideoStream-Worker",
            daemon=True,
        )
        self._thread.start()
        return self

    def stop(self) -> None:
        """Arrête proprement le thread d'acquisition et libère les ressources OpenCV."""
        logger.info("Arrêt demandé pour le flux vidéo...")
        self._stop_event.set()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.5)

        self._release_capture()

        with self._lock:
            self._state = VideoStreamState.STOPPED

        logger.info("VideoStream arrêté avec succès.")

    def change_source(self, new_source: Union[int, str]) -> bool:
        """Bascule dynamiquement vers une nouvelle source vidéo sans couper le thread.

        Args:
            new_source: Nouvelle source (0, URL IP Webcam, RTSP, mock, fichier).

        Returns:
            bool: True si la demande de changement a été acceptée.
        """
        norm_source = self._normalize_source(new_source)
        logger.info(f"Changement dynamique de source vidéo vers : {norm_source}")

        with self._lock:
            self.raw_source = new_source
            self.source = norm_source
            self._is_mock = (str(norm_source).lower() == "mock")
            self._state = VideoStreamState.CONNECTING
            self._reconnect_count = 0
            self._last_error = ""

        # Libère l'ancien capteur pour que la boucle principale se reconnecte
        self._release_capture()
        return True

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        """Récupère la frame la plus récente de manière thread-safe (Zero-Lag).

        Returns:
            Tuple (success, frame):
                - success (bool): True si une frame valide est disponible.
                - frame (np.ndarray): Image OpenCV au format BGR.
        """
        with self._lock:
            if self._latest_frame is None:
                return False, None
            # Copie défensive pour éviter les accès concurrents pendant l'écriture
            frame_copy = self._latest_frame.copy()
            return True, frame_copy

    def read_latest(self) -> Optional[np.ndarray]:
        """Version simplifiée retournant directement l'image ou None."""
        success, frame = self.read()
        return frame if success else None

    def _open_capture(self) -> bool:
        """Instancie et configure cv2.VideoCapture avec optimisations Edge."""
        if self._is_mock:
            with self._lock:
                self._state = VideoStreamState.CONNECTED
                self._actual_resolution = (self.target_width, self.target_height)
            logger.info("Mode simulateur activé (Mire synthétique active).")
            return True

        self._release_capture()
        logger.info(f"Ouverture de la source OpenCV : {self.source}...")

        # Utilisation de FFMPEG avec buffer minimal pour les flux réseaux
        if isinstance(self.source, str) and (
            self.source.startswith("http://")
            or self.source.startswith("https://")
            or self.source.startswith("rtsp://")
        ):
            # Paramètres optimisés pour streaming IP (réduction de latence)
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|analyzeduration;500000|probesize;500000"
            self._cap = cv2.VideoCapture(self.source, cv2.CAP_FFMPEG)
        else:
            self._cap = cv2.VideoCapture(self.source)

        if not self._cap or not self._cap.isOpened():
            err = f"Impossible d'ouvrir le périphérique vidéo : {self.source}"
            logger.error(err)
            with self._lock:
                self._last_error = err
                self._state = VideoStreamState.RECONNECTING
            return False

        # Configuration des propriétés matérielles
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Buffer de 1 frame dans OpenCV
        if isinstance(self.source, int):
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.target_width)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.target_height)
            self._cap.set(cv2.CAP_PROP_FPS, self.target_fps)

        # Lecture de validation
        ret, test_frame = self._cap.read()
        if not ret or test_frame is None:
            err = f"Connexion établie mais impossible de lire la première frame : {self.source}"
            logger.warning(err)
            with self._lock:
                self._last_error = err
            self._release_capture()
            return False

        h, w = test_frame.shape[:2]
        with self._lock:
            self._actual_resolution = (w, h)
            self._state = VideoStreamState.CONNECTED
            self._last_error = ""

        logger.info(f"Flux vidéo connecté avec succès ! Résolution source : {w}x{h}")
        return True

    def _release_capture(self) -> None:
        """Ferme proprement l'objet VideoCapture."""
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception as e:
                logger.debug(f"Erreur lors de la libération de VideoCapture: {e}")
            self._cap = None

    def _capture_loop(self) -> None:
        """Boucle d'acquisition principale exécutée dans le thread dédié."""
        fps_counter: int = 0
        fps_timer: float = time.time()
        loop_delay: float = 1.0 / max(self.target_fps, 1)

        while not self._stop_event.is_set():
            # Si le capteur n'est pas ouvert, tentative de connexion/reconnexion
            if not self._is_mock and (self._cap is None or not self._cap.isOpened()):
                with self._lock:
                    self._state = VideoStreamState.RECONNECTING
                    self._reconnect_count += 1

                logger.warning(
                    f"Tentative de reconnexion #{self._reconnect_count} vers {self.source} "
                    f"dans {self.reconnect_interval}s..."
                )

                # Attente interruptible
                if self._stop_event.wait(timeout=self.reconnect_interval):
                    break

                if not self._open_capture():
                    if self._reconnect_count >= self.max_reconnect_attempts:
                        with self._lock:
                            self._state = VideoStreamState.ERROR
                            self._last_error = f"Échec après {self.max_reconnect_attempts} tentatives de connexion."
                        logger.error(self._last_error)
                    continue

            # Acquisition de la frame
            if self._is_mock:
                frame = self._generate_mock_frame()
                ret = True
                time.sleep(loop_delay)  # Rythme simulé pour respecter target_fps
            else:
                ret, frame = self._cap.read()
                if not ret or frame is None:
                    logger.warning("Perte de signal ou frame corrompue reçue de la source.")
                    self._release_capture()
                    continue

                # Si c'est un fichier vidéo local et qu'il arrive à la fin, on reboucle
                if isinstance(self.source, str) and Path(self.source).is_file():
                    current_pos = self._cap.get(cv2.CAP_PROP_POS_FRAMES)
                    total_pos = self._cap.get(cv2.CAP_PROP_FRAME_COUNT)
                    if current_pos >= total_pos - 1:
                        self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

            # Redimensionnement si configuré pour optimiser l'Edge AI
            if (
                self.target_width > 0
                and self.target_height > 0
                and (frame.shape[1] != self.target_width or frame.shape[0] != self.target_height)
            ):
                frame = cv2.resize(frame, (self.target_width, self.target_height))

            # Mise à jour atomique de la frame avec drop-oldest
            with self._lock:
                if self._has_new_frame:
                    self._total_frames_dropped += 1
                self._latest_frame = frame
                self._has_new_frame = True
                self._last_frame_timestamp = time.time()
                self._total_frames_read += 1
                fps_counter += 1

            # Calcul du FPS réel glissant chaque seconde
            now = time.time()
            if now - fps_timer >= 1.0:
                with self._lock:
                    self._fps_actual = round(fps_counter / (now - fps_timer), 1)
                fps_counter = 0
                fps_timer = now

        self._release_capture()

    def _generate_mock_frame(self) -> np.ndarray:
        """Génère une frame synthétique animée pour les tests et démos sans caméra."""
        w, h = self.target_width, self.target_height
        frame = np.zeros((h, w, 3), dtype=np.uint8)

        # Fond en dégradé sombre Cyber/Edge
        for y in range(h):
            color_val = int(25 + 35 * (y / h))
            frame[y, :] = (color_val, color_val // 2, color_val // 3)

        # Grille cybernétique
        for x in range(0, w, 40):
            cv2.line(frame, (x, 0), (x, h), (40, 45, 55), 1)
        for y in range(0, h, 40):
            cv2.line(frame, (0, y), (w, y), (40, 45, 55), 1)

        # Bande de mires de couleur en bas
        bar_height = 25
        colors = [
            (255, 255, 255), (0, 255, 255), (255, 255, 0), (0, 255, 0),
            (255, 0, 255), (0, 0, 255), (255, 0, 0), (0, 0, 0)
        ]
        bar_w = w // len(colors)
        for i, col in enumerate(colors):
            cv2.rectangle(frame, (i * bar_w, h - bar_height), ((i + 1) * bar_w, h), col, -1)

        # Balle / Cible animée en mouvement pour simuler une présence
        self._mock_pos_x += self._mock_dir_x
        self._mock_pos_y += self._mock_dir_y
        if self._mock_pos_x <= 40 or self._mock_pos_x >= w - 40:
            self._mock_dir_x *= -1
        if self._mock_pos_y <= 60 or self._mock_pos_y >= h - 60:
            self._mock_dir_y *= -1

        # Dessin d'une silhouette simulée (cible de test)
        center_x, center_y = self._mock_pos_x, self._mock_pos_y
        cv2.circle(frame, (center_x, center_y - 20), 16, (0, 220, 255), -1)  # Tête
        cv2.ellipse(frame, (center_x, center_y + 15), (22, 35), 0, 0, 360, (0, 180, 230), -1)  # Buste
        cv2.putText(frame, "SIMULATION HUMAIN", (center_x - 65, center_y - 45),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 220, 255), 1, cv2.LINE_AA)

        # En-tête Sentinel-Edge
        cv2.rectangle(frame, (0, 0), (w, 35), (20, 20, 25), -1)
        cv2.putText(frame, "SENTINEL-EDGE | MIRE SYNTHÉTIQUE V0 (AMADOU H TRAORE)",
                    (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 200), 1, cv2.LINE_AA)

        # Horodatage temps réel
        time_str = time.strftime("%Y-%m-%d %H:%M:%S")
        cv2.putText(frame, f"REC [LIVE]: {time_str}", (w - 230, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1, cv2.LINE_AA)

        return frame

    def save_snapshot(self, output_dir: Optional[Union[str, Path]] = None) -> Optional[str]:
        """Capture et enregistre un snapshot de la frame actuelle sur disque.

        Args:
            output_dir: Dossier de destination (utilise config.CAPTURE_DIR par défaut).

        Returns:
            Optional[str]: Chemin absolu du fichier enregistré, ou None en cas d'échec.
        """
        success, frame = self.read()
        if not success or frame is None:
            logger.warning("Impossible de prendre un snapshot : aucune frame disponible.")
            return None

        target_dir = Path(output_dir or "captures")
        target_dir.mkdir(parents=True, exist_ok=True)

        filename = f"snapshot_{time.strftime('%Y%m%d_%H%M%S')}_{int((time.time() % 1) * 1000):03d}.jpg"
        filepath = target_dir / filename

        # Ajout d'un bandeau horodaté sur le snapshot officiel
        annotated_snapshot = frame.copy()
        stamp = f"Sentinel-Edge Capture | {time.strftime('%Y-%m-%d %H:%M:%S')}"
        cv2.putText(
            annotated_snapshot,
            stamp,
            (15, annotated_snapshot.shape[0] - 15),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 255, 0),
            1,
            cv2.LINE_AA,
        )

        success_write = cv2.imwrite(str(filepath), annotated_snapshot)
        if success_write:
            logger.info(f"Snapshot sauvegardé : {filepath}")
            return str(filepath)
        return None

    def get_telemetry(self) -> Dict[str, Any]:
        """Génère un dictionnaire complet des métriques pour le Dashboard Web et l'API."""
        with self._lock:
            uptime = round(time.time() - self._start_time, 1) if self._start_time > 0 else 0.0
            source_type = "Webcam USB/Locale"
            source_str = str(self.source)
            if self._is_mock:
                source_type = "Mire Synthétique (Mock)"
            elif source_str.startswith("http://") or source_str.startswith("https://"):
                source_type = "IP Webcam Android (Wi-Fi)"
            elif source_str.startswith("rtsp://"):
                source_type = "Caméra IP RTSP"
            elif Path(source_str).is_file():
                source_type = "Fichier Vidéo de Test"

            return {
                "source": self.raw_source,
                "source_type": source_type,
                "state": self._state,
                "fps": self._fps_actual,
                "resolution": f"{self._actual_resolution[0]}x{self._actual_resolution[1]}",
                "total_frames": self._total_frames_read,
                "dropped_frames": self._total_frames_dropped,
                "reconnect_count": self._reconnect_count,
                "uptime_seconds": uptime,
                "last_error": self._last_error,
                "is_mock": self._is_mock,
            }

    def __enter__(self) -> "VideoStream":
        return self.start()

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()


# =====================================================================
# Banc d'essai autonome en ligne de commande
# =====================================================================
if __name__ == "__main__":
    src_arg = sys.argv[1] if len(sys.argv) > 1 else "0"
    print("=" * 65)
    print("  SENTINEL-EDGE — Banc d'essai VideoStream (Thread 1)")
    print(f"  Auteur : AMADOU H TRAORE | Source : {src_arg}")
    print("=" * 65)

    stream = VideoStream(source=src_arg, target_width=640, target_height=480)
    stream.start()

    try:
        start_t = time.time()
        while time.time() - start_t < 10:
            time.sleep(1)
            telemetry = stream.get_telemetry()
            print(
                f"[{telemetry['state']}] Source: {telemetry['source_type']} | "
                f"FPS: {telemetry['fps']} | "
                f"Frames: {telemetry['total_frames']} (Drops: {telemetry['dropped_frames']})"
            )
    except KeyboardInterrupt:
        print("\nArrêt demandé par l'utilisateur.")
    finally:
        stream.stop()
        print("Test terminé.")
