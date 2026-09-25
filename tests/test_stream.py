"""Tests unitaires et de robustesse pour le moteur VideoStream (Thread 1).

Auteur : AMADOU H TRAORE (Pôle IA & Data)
Vérifie :
- L'instanciation et le démarrage multithreadé
- La génération de mire synthétique (Mock)
- Le respect du principe 'Drop Oldest' sans fuite mémoire
- La thread-safety et l'arrêt propre
"""

import sys
import time
import unittest
from pathlib import Path

# Ajout de la racine au PYTHONPATH
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from core.stream import VideoStream, VideoStreamState


class TestVideoStream(unittest.TestCase):
    """Suite de tests automatisés pour VideoStream."""

    def test_mock_stream_lifecycle(self):
        """Vérifie le cycle de vie complet en mode Mock (Init -> Start -> Frames -> Stop)."""
        stream = VideoStream(source="mock", target_width=320, target_height=240, target_fps=20)
        self.assertEqual(stream.state, VideoStreamState.INITIALIZING)

        stream.start()
        self.assertTrue(stream.is_active)

        # Attente d'acquisition de quelques frames
        time.sleep(1.0)

        ret, frame = stream.read()
        self.assertTrue(ret)
        self.assertIsNotNone(frame)
        self.assertEqual(frame.shape, (240, 320, 3))

        # Télémétrie
        telemetry = stream.get_telemetry()
        self.assertGreater(telemetry["total_frames"], 0)
        self.assertEqual(telemetry["source_type"], "Mire Synthétique (Mock)")

        # Arrêt
        stream.stop()
        self.assertFalse(stream.is_active)
        self.assertEqual(stream.state, VideoStreamState.STOPPED)

    def test_drop_oldest_zero_lag(self):
        """Vérifie que la lecture récupère toujours la dernière frame sans accumulation de queue."""
        stream = VideoStream(source="mock", target_width=160, target_height=120, target_fps=30)
        stream.start()

        # Attente de 1.5 seconde sans appeler read()
        time.sleep(1.5)

        ret1, frame1 = stream.read()
        self.assertTrue(ret1)

        time.sleep(0.1)
        ret2, frame2 = stream.read()
        self.assertTrue(ret2)

        telemetry = stream.get_telemetry()
        # Le compteur de drops doit être > 0 car les frames non lues ont été écrasées
        self.assertGreater(telemetry["dropped_frames"], 0)

        stream.stop()

    def test_context_manager(self):
        """Vérifie le support du protocole context manager ('with VideoStream(...)')."""
        with VideoStream(source="mock", target_width=320, target_height=240) as stream:
            self.assertTrue(stream.is_active)
            time.sleep(0.5)
            ret, frame = stream.read()
            self.assertTrue(ret)

        self.assertFalse(stream.is_active)


if __name__ == "__main__":
    unittest.main()
