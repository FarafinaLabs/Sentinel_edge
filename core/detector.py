"""Module de détection d'intrusion optimisé pour l'Edge AI (Sentinel-Edge).

Fournit la classe IntrusionDetector exploitant YOLOv8n pour la détection
stricte d'humains avec filtrage par seuil de confiance et persistance
temporelle anti-faux positifs.
"""

from typing import Tuple, Union
from pathlib import Path
import sys
import time
import cv2
import numpy as np
from ultralytics import YOLO


class IntrusionDetector:
    """Détecteur d'intrusion humaine basé sur YOLOv8 avec persistance temporelle.

    Cette classe encapsule l'inférence YOLOv8n optimisée pour CPU et applique une
    politique de confirmation temporelle afin d'éliminer les faux positifs
    (bruits de capteur, ombres éphémères, etc.).

    Attributes:
        TARGET_CLASS_ID (int): Identifiant COCO de la classe ciblée (0 pour 'person').
        model (YOLO): Instance du modèle Ultralytics YOLOv8.
        conf_thresh (float): Seuil minimal de confiance pour valider une détection.
        persistence (int): Nombre minimal de frames consécutives requises
            pour confirmer une intrusion.
        device (str): Périphérique d'inférence ('cpu', 'cuda', etc.).
        consecutive_hits (int): Compteur interne de détections consécutives.
    """

    TARGET_CLASS_ID: int = 0  # 0 correspond à 'person' dans le jeu de données COCO

    def __init__(
        self,
        model_name: Union[str, Path] = "yolov8n.pt",
        conf_thresh: float = 0.60,
        persistence: int = 2,
        device: str = "cpu",
    ) -> None:
        """Initialise le détecteur d'intrusion.

        Args:
            model_name: Chemin ou identifiant du modèle YOLO (ex: 'yolov8n.pt').
            conf_thresh: Seuil de confiance minimal (0.0 à 1.0). Par défaut 0.60.
            persistence: Nombre de frames consécutives avec détection pour valider l'alerte.
                Par défaut 2.
            device: Cible matérielle pour l'inférence ('cpu' par défaut pour les contraintes Edge).

        Raises:
            ValueError: Si conf_thresh n'est pas dans [0.0, 1.0] ou persistence < 1.
        """
        if not (0.0 <= conf_thresh <= 1.0):
            raise ValueError(f"conf_thresh doit être compris entre 0.0 et 1.0 (reçu: {conf_thresh})")
        if persistence < 1:
            raise ValueError(f"persistence doit être au moins égal à 1 (reçu: {persistence})")

        self.conf_thresh: float = float(conf_thresh)
        self.persistence: int = int(persistence)
        self.device: str = device
        self.consecutive_hits: int = 0

        # Chargement du modèle YOLOv8
        self.model: YOLO = YOLO(str(model_name))

    def process_frame(self, frame: np.ndarray) -> Tuple[bool, float, np.ndarray]:
        """Traite une frame vidéo, détecte les humains et applique la persistance temporelle.

        Exécute l'inférence avec filtrage direct de la classe 'person' (COCO 0),
        dessine les boîtes englobantes rouges et les annotations de confiance sur
        l'image, et met à jour le compteur temporel anti-faux positifs.

        Args:
            frame: Image OpenCV au format BGR (numpy.ndarray).

        Returns:
            Tuple contenant :
                - is_confirmed (bool): True si une intrusion est validée
                  (consecutive_hits >= persistence), False sinon.
                - highest_conf (float): Score de confiance maximal parmi les humains détectés
                  (0.0 si aucun humain n'est détecté).
                - annotated_frame (np.ndarray): Copie de la frame avec les boîtes
                  englobantes rouges et labels "Humain: <conf>".

        Raises:
            ValueError: Si la frame fournie est None ou de dimensions nulles.
        """
        if frame is None or frame.size == 0:
            raise ValueError("La frame fournie est vide ou invalide.")

        # Inférence YOLOv8 optimisée CPU :
        # - classes=[0] : filtre uniquement la classe 'person' au niveau du NMS
        # - conf=self.conf_thresh : ignore les prédictions en dessous du seuil
        # - verbose=False : désactive les logs console pour maximiser les performances
        results = self.model(
            source=frame,
            classes=[self.TARGET_CLASS_ID],
            conf=self.conf_thresh,
            device=self.device,
            verbose=False,
        )

        detected: bool = False
        highest_conf: float = 0.0
        annotated_frame: np.ndarray = frame.copy()

        # Analyse des résultats d'inférence
        for result in results:
            boxes = result.boxes
            if boxes is None or len(boxes) == 0:
                continue

            for box in boxes:
                detected = True
                conf = float(box.conf[0].item()) if hasattr(box.conf[0], "item") else float(box.conf[0])
                if conf > highest_conf:
                    highest_conf = conf

                # Coordonnées de la boîte englobante (x1, y1, x2, y2)
                xyxy = box.xyxy[0].tolist() if hasattr(box.xyxy[0], "tolist") else box.xyxy[0]
                x1, y1, x2, y2 = map(int, xyxy)

                # Couleur BGR rouge pour l'alerte intrusion : (0, 0, 255)
                box_color = (0, 0, 255)
                cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), box_color, 2)

                # Formatage du label avec score arrondi à 2 décimales
                label = f"Humain: {conf:.2f}"

                # Calcul des dimensions du texte pour positionnement optimal
                (text_w, text_h), baseline = cv2.getTextSize(
                    label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1
                )
                text_y = max(y1 - 6, text_h + 4)

                # Fond semi-opaque / aplat rouge pour lisibilité industrielle
                cv2.rectangle(
                    annotated_frame,
                    (x1, text_y - text_h - 4),
                    (x1 + text_w + 4, text_y + baseline),
                    box_color,
                    -1,
                )
                # Texte en blanc sur cartouche rouge
                cv2.putText(
                    annotated_frame,
                    label,
                    (x1 + 2, text_y - 2),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (255, 255, 255),
                    1,
                    cv2.LINE_AA,
                )

        # Logique de persistance temporelle anti-faux positifs
        if detected:
            self.consecutive_hits += 1
        else:
            self.consecutive_hits = 0

        # L'intrusion est confirmée dès que la persistance requise est atteinte
        is_confirmed: bool = self.consecutive_hits >= self.persistence

        return is_confirmed, highest_conf, annotated_frame

    def reset(self) -> None:
        """Réinitialise manuellement l'état temporel du détecteur."""
        self.consecutive_hits = 0


# =====================================================================
# Bloc de test autonome (Webcam locale & benchmark temps réel)
# =====================================================================
if __name__ == "__main__":
    # Source vidéo : 0 par défaut (webcam locale) ou argument CLI
    video_source: Union[int, str] = 0
    if len(sys.argv) > 1:
        arg_src = sys.argv[1]
        video_source = int(arg_src) if arg_src.isdigit() else arg_src

    print("=" * 65)
    print("  SENTINEL-EDGE — Banc d'essai autonome : IntrusionDetector")
    print(f"  Source vidéo sélectionnée : {video_source}")
    print("=" * 65)

    try:
        detector = IntrusionDetector(
            model_name="yolov8n.pt",
            conf_thresh=0.60,
            persistence=2,
            device="cpu",
        )
    except Exception as exc:
        print(f"[ERREUR] Échec du chargement du modèle : {exc}")
        sys.exit(1)

    cap = cv2.VideoCapture(video_source)
    if not cap.isOpened():
        print(f"[ERREUR] Impossible d'ouvrir la source vidéo : {video_source}")
        print("Vérifiez la connexion de la webcam ou l'accès aux périphériques vidéo.")
        sys.exit(1)

    # Réglage de la résolution pour fluidité Edge (720p / standard)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    print("[INFO] Démarrage du flux. Commandes clavier :")
    print("       - 'q' ou 'Echap' : Quitter l'application")
    print("       - 'r'           : Réinitialiser le compteur de persistance\n")

    # Variables de calcul du FPS lissé
    prev_time = time.time()
    fps_smooth = 0.0
    alpha = 0.1  # Facteur de lissage exponentiel pour le FPS

    try:
        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                print("[ATTENTION] Frame non reçue, fin du flux ou déconnexion...")
                break

            curr_time = time.time()
            elapsed = curr_time - prev_time
            prev_time = curr_time
            instant_fps = (1.0 / elapsed) if elapsed > 0 else 0.0
            fps_smooth = (alpha * instant_fps) + ((1.0 - alpha) * fps_smooth)

            # Inférence et filtrage
            is_confirmed, highest_conf, annotated_frame = detector.process_frame(frame)

            # Incrustation HUD (Head-Up Display) d'information et d'alerte
            h, w = annotated_frame.shape[:2]

            # Bandeau supérieur semi-transparent
            overlay = annotated_frame.copy()
            cv2.rectangle(overlay, (0, 0), (w, 50), (20, 20, 20), -1)
            cv2.addWeighted(overlay, 0.7, annotated_frame, 0.3, 0, annotated_frame)

            # Indicateur de statut
            if is_confirmed:
                status_text = "STATUT : [ALERTE INTRUSION CONFIRMEE]"
                status_color = (0, 0, 255)  # Rouge
            elif detector.consecutive_hits > 0:
                status_text = f"STATUT : [DETECTION EN COURS - {detector.consecutive_hits}/{detector.persistence}]"
                status_color = (0, 165, 255)  # Orange
            else:
                status_text = "STATUT : [VEILLE - AUCUNE INTRUSION]"
                status_color = (0, 255, 0)  # Vert

            cv2.putText(
                annotated_frame,
                status_text,
                (15, 32),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                status_color,
                2,
                cv2.LINE_AA,
            )

            # Métriques : FPS, Score max et Persistance
            metrics_text = (
                f"FPS: {fps_smooth:.1f} | Conf. Max: {highest_conf:.2f} | "
                f"Hits: {detector.consecutive_hits}/{detector.persistence}"
            )
            (m_w, _), _ = cv2.getTextSize(metrics_text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
            cv2.putText(
                annotated_frame,
                metrics_text,
                (w - m_w - 15, 32),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )

            cv2.imshow("Sentinel-Edge - IntrusionDetector (Test Standalone)", annotated_frame)

            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), ord("Q"), 27):  # 'q' ou Echap
                print("[INFO] Arrêt demandé par l'utilisateur.")
                break
            elif key in (ord("r"), ord("R")):
                detector.reset()
                print("[INFO] Compteur temporel réinitialisé.")

    finally:
        cap.release()
        cv2.destroyAllWindows()
        print("[INFO] Ressources vidéo libérées avec succès. Fermeture.")
