"""Simulateur de flux HTTP IP Webcam Android (pour tests et démos locales).

Auteur : AMADOU H TRAORE (Pôle IA)
Ce script lance un mini-serveur HTTP local émulant fidèlement le comportement
de l'application Android 'IP Webcam' sur l'URL :
http://127.0.0.1:8089/video
"""

import time
import numpy as np
import cv2
from flask import Flask, Response

mock_app = Flask(__name__)

def generate_mock_ip_feed():
    """Génère un flux MJPEG avec timer et cible mobile."""
    w, h = 640, 480
    pos_x, pos_y = 100, 100
    dir_x, dir_y = 6, 4

    while True:
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        frame[:] = (30, 25, 20)  # Fond sombre

        # Cible animée
        pos_x += dir_x
        pos_y += dir_y
        if pos_x <= 30 or pos_x >= w - 30:
            dir_x *= -1
        if pos_y <= 50 or pos_y >= h - 50:
            dir_y *= -1

        cv2.circle(frame, (pos_x, pos_y), 25, (0, 165, 255), -1)
        cv2.putText(frame, "CIBLE SIMULEE", (pos_x - 50, pos_y - 35),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 165, 255), 1)

        # En-tête IP Webcam
        cv2.putText(frame, "IP WEBCAM ANDROID SIMULATOR (8089/video)", (20, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        cv2.putText(frame, f"HORODATAGE: {time.strftime('%H:%M:%S')}", (20, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        ret, buffer = cv2.imencode(".jpg", frame)
        if ret:
            yield (b"--frame\r\n"
                   b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n")
        time.sleep(0.033)  # ~30 FPS

@mock_app.route("/video")
def video():
    return Response(generate_mock_ip_feed(), mimetype="multipart/x-mixed-replace; boundary=frame")

if __name__ == "__main__":
    print("Démarrage du simulateur IP Webcam sur http://127.0.0.1:8089/video")
    mock_app.run(host="127.0.0.1", port=8089)
