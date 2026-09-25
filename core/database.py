"""Module de persistance SQLite3 pour Sentinel-Edge.

Développé par AMADOU H TRAORE — Pôle Télécom, Réseau & Sécurité.
Implémente la journalisation persistante de chaque événement d'intrusion
dans une base de données relationnelle locale légère (SQLite3) :
- Création automatique du schéma à l'initialisation
- Insertion thread-safe des événements détectés
- Requêtes de consultation pour le Dashboard (historique, statistiques)
- Conservation des métadonnées : id, date/heure, score de confiance, chemin cliché
"""

import time
import sqlite3
import logging
import threading
from pathlib import Path
from typing import List, Dict, Any, Optional

# Configuration des logs du module
logger = logging.getLogger("Sentinel.Database")


class SentinelDatabase:
    """Gestionnaire de base de données SQLite3 thread-safe pour Sentinel-Edge.

    Persiste les événements d'intrusion avec leurs métadonnées pour
    consultation ultérieure via le Dashboard web.

    Attributes:
        db_path (str): Chemin vers le fichier de base de données SQLite.
    """

    # Schéma SQL de la table des événements d'intrusion
    SCHEMA_SQL = """
    CREATE TABLE IF NOT EXISTS intrusion_events (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp       TEXT    NOT NULL,
        confidence      REAL    NOT NULL,
        image_path      TEXT,
        source          TEXT    DEFAULT 'unknown',
        telegram_sent   INTEGER DEFAULT 0,
        created_at      REAL    NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_events_timestamp
        ON intrusion_events(timestamp DESC);

    CREATE INDEX IF NOT EXISTS idx_events_confidence
        ON intrusion_events(confidence);
    """

    def __init__(self, db_path: str = "sentinel.db") -> None:
        """Initialise la base de données et crée le schéma si nécessaire.

        Args:
            db_path: Chemin vers le fichier SQLite (créé automatiquement).
        """
        self.db_path: str = db_path
        self._lock = threading.Lock()

        # Création du répertoire parent si nécessaire
        db_file = Path(db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)

        # Initialisation du schéma
        self._init_schema()
        logger.info(f"Base de données Sentinel initialisée : {db_path}")

    def _get_connection(self) -> sqlite3.Connection:
        """Crée une nouvelle connexion SQLite configurée pour la performance."""
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")  # Write-Ahead Logging pour la concurrence
        conn.execute("PRAGMA synchronous=NORMAL")  # Bon compromis performance/sécurité
        return conn

    def _init_schema(self) -> None:
        """Crée les tables et index si inexistants."""
        try:
            with self._lock:
                conn = self._get_connection()
                conn.executescript(self.SCHEMA_SQL)
                conn.commit()
                conn.close()
            logger.info("Schéma de base de données vérifié/créé avec succès.")
        except sqlite3.Error as e:
            logger.error(f"Erreur lors de l'initialisation du schéma : {e}")
            raise

    def log_intrusion(
        self,
        confidence: float,
        image_path: Optional[str] = None,
        source: str = "unknown",
        telegram_sent: bool = False,
    ) -> Optional[int]:
        """Enregistre un événement d'intrusion confirmé dans la base.

        Args:
            confidence: Score de confiance maximal de la détection (0.0-1.0).
            image_path: Chemin vers le snapshot enregistré (peut être None).
            source: Description de la source vidéo active.
            telegram_sent: True si l'alerte Telegram a été envoyée avec succès.

        Returns:
            int: L'ID de l'événement inséré, ou None en cas d'erreur.
        """
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        created_at = time.time()

        try:
            with self._lock:
                conn = self._get_connection()
                cursor = conn.execute(
                    """INSERT INTO intrusion_events
                       (timestamp, confidence, image_path, source, telegram_sent, created_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (timestamp, confidence, image_path, source, int(telegram_sent), created_at),
                )
                event_id = cursor.lastrowid
                conn.commit()
                conn.close()

            logger.info(
                f"Événement d'intrusion enregistré (id={event_id}, "
                f"confiance={confidence:.2f}, telegram={'oui' if telegram_sent else 'non'})"
            )
            return event_id

        except sqlite3.Error as e:
            logger.error(f"Erreur d'insertion dans la base : {e}")
            return None

    def get_recent_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Récupère les derniers événements d'intrusion.

        Args:
            limit: Nombre maximal d'événements à retourner.

        Returns:
            Liste de dictionnaires contenant les métadonnées de chaque événement.
        """
        try:
            with self._lock:
                conn = self._get_connection()
                cursor = conn.execute(
                    """SELECT id, timestamp, confidence, image_path, source,
                              telegram_sent, created_at
                       FROM intrusion_events
                       ORDER BY created_at DESC
                       LIMIT ?""",
                    (limit,),
                )
                rows = cursor.fetchall()
                conn.close()

            return [
                {
                    "id": row["id"],
                    "timestamp": row["timestamp"],
                    "confidence": round(row["confidence"], 4),
                    "image_path": row["image_path"],
                    "source": row["source"],
                    "telegram_sent": bool(row["telegram_sent"]),
                    "image_url": f"/captures/{Path(row['image_path']).name}"
                    if row["image_path"]
                    else None,
                }
                for row in rows
            ]

        except sqlite3.Error as e:
            logger.error(f"Erreur de lecture des événements : {e}")
            return []

    def get_event_count(self) -> int:
        """Retourne le nombre total d'événements enregistrés."""
        try:
            with self._lock:
                conn = self._get_connection()
                cursor = conn.execute("SELECT COUNT(*) AS cnt FROM intrusion_events")
                count = cursor.fetchone()["cnt"]
                conn.close()
            return count
        except sqlite3.Error as e:
            logger.error(f"Erreur lors du comptage : {e}")
            return 0

    def get_stats(self) -> Dict[str, Any]:
        """Retourne des statistiques agrégées pour le Dashboard."""
        try:
            with self._lock:
                conn = self._get_connection()
                cursor = conn.execute(
                    """SELECT
                        COUNT(*) AS total_events,
                        COALESCE(AVG(confidence), 0) AS avg_confidence,
                        COALESCE(MAX(confidence), 0) AS max_confidence,
                        SUM(CASE WHEN telegram_sent = 1 THEN 1 ELSE 0 END) AS telegram_sent_count,
                        MIN(timestamp) AS first_event,
                        MAX(timestamp) AS last_event
                    FROM intrusion_events"""
                )
                row = cursor.fetchone()
                conn.close()

            return {
                "total_events": row["total_events"],
                "avg_confidence": round(row["avg_confidence"], 4),
                "max_confidence": round(row["max_confidence"], 4),
                "telegram_sent_count": row["telegram_sent_count"] or 0,
                "first_event": row["first_event"],
                "last_event": row["last_event"],
                "db_path": self.db_path,
            }

        except sqlite3.Error as e:
            logger.error(f"Erreur lors du calcul des statistiques : {e}")
            return {
                "total_events": 0,
                "avg_confidence": 0,
                "max_confidence": 0,
                "telegram_sent_count": 0,
                "first_event": None,
                "last_event": None,
                "db_path": self.db_path,
            }

    def clear_all(self) -> bool:
        """Supprime tous les événements (pour les tests ou le reset)."""
        try:
            with self._lock:
                conn = self._get_connection()
                conn.execute("DELETE FROM intrusion_events")
                conn.commit()
                conn.close()
            logger.warning("Tous les événements ont été supprimés de la base.")
            return True
        except sqlite3.Error as e:
            logger.error(f"Erreur lors de la suppression : {e}")
            return False


# =====================================================================
# Banc d'essai autonome
# =====================================================================
if __name__ == "__main__":
    import sys
    import tempfile
    import os

    print("=" * 65)
    print("  SENTINEL-EDGE — Test du Module Base de Données SQLite")
    print("  Auteur : AMADOU H TRAORE (Pôle Télécom & Sécurité)")
    print("=" * 65)

    # Utilisation d'une base temporaire pour les tests
    test_db_path = os.path.join(
        str(Path(__file__).resolve().parent.parent), "test_sentinel.db"
    )

    print(f"\n[1/5] Initialisation de la base : {test_db_path}")
    db = SentinelDatabase(db_path=test_db_path)
    print("  ✅ Base créée avec succès.")

    print("\n[2/5] Insertion d'événements de test...")
    id1 = db.log_intrusion(confidence=0.85, image_path="/tmp/test1.jpg", source="webcam 0")
    id2 = db.log_intrusion(confidence=0.72, image_path="/tmp/test2.jpg", source="mock", telegram_sent=True)
    id3 = db.log_intrusion(confidence=0.91, source="rtsp://camera1")
    print(f"  ✅ 3 événements insérés (IDs: {id1}, {id2}, {id3})")

    print("\n[3/5] Lecture des événements récents...")
    events = db.get_recent_events(limit=10)
    for ev in events:
        print(f"  #{ev['id']} | {ev['timestamp']} | Conf: {ev['confidence']:.2f} | "
              f"Telegram: {'✅' if ev['telegram_sent'] else '❌'} | Source: {ev['source']}")

    print(f"\n[4/5] Nombre total d'événements : {db.get_event_count()}")

    print("\n[5/5] Statistiques agrégées :")
    stats = db.get_stats()
    for key, val in stats.items():
        print(f"  {key}: {val}")

    # Nettoyage
    db.clear_all()
    os.remove(test_db_path)
    print("\n✅ Test terminé avec succès. Base temporaire supprimée.")
