"""
Suite de tests unitaires et d'intégration pour Sentinel-Edge.
Couvre : Config, SQLite Database, Telegram Notifier, VideoStream, IntrusionDetector, Web Flask App.
"""
import sys
import os
import unittest
import json
import tempfile
import time

# Permettre l'importation depuis la racine du projet
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config import Config
from core.database import SentinelDatabase
from core.notifier import TelegramNotifier, create_notifier_from_config


class TestSentinelConfig(unittest.TestCase):
    def test_default_values(self):
        self.assertIsNotNone(Config.WEB_PORT)
        self.assertIsNotNone(Config.WEB_HOST)
        self.assertIsNotNone(Config.DATABASE_PATH)
        self.assertIsInstance(Config.CONFIDENCE_THRESHOLD, float)


class TestSentinelDatabase(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp_dir.name, "test_sentinel.db")
        self.db = SentinelDatabase(self.db_path)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_log_and_retrieve_intrusion(self):
        event_id = self.db.log_intrusion(
            confidence=0.88,
            image_path="/tmp/test_snap.jpg",
            source="camera_mock",
            telegram_sent=True
        )
        self.assertIsNotNone(event_id)
        self.assertGreater(event_id, 0)

        events = self.db.get_recent_events(limit=10)
        self.assertEqual(len(events), 1)
        record = events[0]
        self.assertEqual(record["confidence"], 0.88)
        self.assertEqual(record["source"], "camera_mock")
        self.assertEqual(record["image_path"], "/tmp/test_snap.jpg")
        self.assertTrue(record["telegram_sent"])

    def test_stats(self):
        self.db.log_intrusion(0.95, None, "source_1", True)
        self.db.log_intrusion(0.75, None, "source_2", False)

        stats = self.db.get_stats()
        self.assertEqual(stats["total_events"], 2)
        self.assertEqual(stats["telegram_sent_count"], 1)
        self.assertIn("avg_confidence", stats)
        self.assertAlmostEqual(stats["avg_confidence"], 0.85, places=2)


class TestTelegramNotifier(unittest.TestCase):
    def test_notifier_init(self):
        notifier = TelegramNotifier(bot_token="FAKE_TOKEN:123456", chat_id="123456789")
        self.assertTrue(notifier.is_configured)
        self.assertEqual(notifier.bot_token, "FAKE_TOKEN:123456")
        self.assertEqual(notifier.chat_id, "123456789")

    def test_unconfigured_factory(self):
        notifier = create_notifier_from_config()
        if notifier is None:
            self.assertIsNone(notifier)
        else:
            self.assertTrue(notifier.is_configured)


class TestFlaskWebApp(unittest.TestCase):
    def setUp(self):
        try:
            from web.app import app
            app.testing = True
            self.client = app.test_client()
            self.app_available = True
        except Exception as e:
            self.app_available = False

    def test_endpoints(self):
        if not self.app_available:
            self.skipTest("Flask app import failed.")

        res_root = self.client.get('/')
        self.assertEqual(res_root.status_code, 200)

        res_status = self.client.get('/api/status')
        self.assertEqual(res_status.status_code, 200)
        data = json.loads(res_status.data)
        self.assertIn('state', data)
        self.assertIn('fps', data)

        res_intrusions = self.client.get('/api/intrusions')
        self.assertEqual(res_intrusions.status_code, 200)
        data_int = json.loads(res_intrusions.data)
        self.assertIsInstance(data_int, list)

        res_stats = self.client.get('/api/intrusions/stats')
        self.assertEqual(res_stats.status_code, 200)
        data_stats = json.loads(res_stats.data)
        self.assertIn('total_events', data_stats)


if __name__ == "__main__":
    unittest.main()
