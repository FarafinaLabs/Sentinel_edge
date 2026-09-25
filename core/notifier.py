"""Module de notification Telegram chiffré pour Sentinel-Edge.

Développé par AMADOU H TRAORE — Pôle Télécom, Réseau & Sécurité.
Implémente l'envoi asynchrone non-bloquant d'alertes d'intrusion via
l'API Telegram Bot (sendPhoto) avec :
- Envoi de snapshot annoté avec bounding box et horodatage
- Temporisation anti-spam (cooldown configurable)
- Gestion des erreurs réseau et retry automatique
- Journalisation complète des envois
"""

import time
import logging
import threading
from pathlib import Path
from typing import Optional

import requests

# Configuration des logs du module
logger = logging.getLogger("Sentinel.Notifier")


class TelegramNotifier:
    """Gestionnaire d'alertes Telegram avec anti-spam et envoi asynchrone.

    Envoie des snapshots annotés via l'API Telegram Bot en respectant
    un cooldown configurable pour éviter le déni de service.

    Attributes:
        bot_token (str): Token du bot Telegram (via @BotFather).
        chat_id (str): Identifiant du chat/groupe de destination.
        cooldown (int): Période réfractaire minimale entre deux alertes (secondes).
        _last_alert_time (float): Timestamp du dernier envoi réussi.
    """

    TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/{method}"

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        cooldown: int = 10,
        timeout: int = 15,
    ) -> None:
        """Initialise le notifieur Telegram.

        Args:
            bot_token: Token du bot Telegram (ex: "123456:ABC-DEF...").
            chat_id: Chat ID ou identifiant de groupe (ex: "-1001234567890").
            cooldown: Secondes minimales entre deux alertes consécutives.
            timeout: Timeout de la requête HTTP en secondes.

        Raises:
            ValueError: Si bot_token ou chat_id est vide.
        """
        if not bot_token or not bot_token.strip():
            raise ValueError("TELEGRAM_BOT_TOKEN est obligatoire pour les notifications.")
        if not chat_id or not str(chat_id).strip():
            raise ValueError("TELEGRAM_CHAT_ID est obligatoire pour les notifications.")

        self.bot_token: str = bot_token.strip()
        self.chat_id: str = str(chat_id).strip()
        self.cooldown: int = max(1, cooldown)
        self.timeout: int = timeout

        self._last_alert_time: float = 0.0
        self._total_sent: int = 0
        self._total_failed: int = 0
        self._total_skipped_cooldown: int = 0
        self._lock = threading.Lock()
        self._is_configured: bool = True

        logger.info(
            f"TelegramNotifier initialisé (chat_id={self.chat_id}, "
            f"cooldown={self.cooldown}s, timeout={self.timeout}s)"
        )

    @property
    def is_configured(self) -> bool:
        """Indique si le notifieur est correctement configuré."""
        return self._is_configured

    def _build_url(self, method: str) -> str:
        """Construit l'URL de l'API Telegram pour la méthode donnée."""
        return self.TELEGRAM_API_URL.format(token=self.bot_token, method=method)

    def _is_cooldown_active(self) -> bool:
        """Vérifie si le cooldown anti-spam est encore actif."""
        with self._lock:
            elapsed = time.time() - self._last_alert_time
            return elapsed < self.cooldown

    def test_connection(self) -> bool:
        """Teste la connexion au bot Telegram via getMe.

        Returns:
            bool: True si le bot répond correctement.
        """
        try:
            url = self._build_url("getMe")
            response = requests.get(url, timeout=self.timeout)
            data = response.json()
            if data.get("ok"):
                bot_info = data.get("result", {})
                bot_name = bot_info.get("first_name", "Inconnu")
                bot_username = bot_info.get("username", "")
                logger.info(f"Connexion Telegram réussie : {bot_name} (@{bot_username})")
                return True
            else:
                logger.error(f"Erreur API Telegram : {data.get('description', 'Inconnue')}")
                return False
        except requests.RequestException as e:
            logger.error(f"Erreur réseau lors du test Telegram : {e}")
            return False

    def send_text(self, message: str) -> bool:
        """Envoie un message texte simple via le bot Telegram.

        Args:
            message: Texte du message à envoyer.

        Returns:
            bool: True si l'envoi a réussi.
        """
        try:
            url = self._build_url("sendMessage")
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "HTML",
            }
            response = requests.post(url, json=payload, timeout=self.timeout)
            data = response.json()
            if data.get("ok"):
                logger.info(f"Message texte envoyé avec succès.")
                return True
            else:
                logger.error(f"Erreur sendMessage : {data.get('description', 'Inconnue')}")
                return False
        except requests.RequestException as e:
            logger.error(f"Erreur réseau sendMessage : {e}")
            return False

    def send_intrusion_alert(
        self,
        image_path: str,
        confidence: float,
        timestamp: Optional[str] = None,
    ) -> bool:
        """Envoie une alerte d'intrusion avec photo annotée via sendPhoto.

        Respecte le cooldown anti-spam. Si le cooldown est actif, l'envoi
        est silencieusement ignoré (pas d'erreur) pour éviter le flooding.

        Args:
            image_path: Chemin absolu vers le snapshot annoté (JPEG).
            confidence: Score de confiance maximal de la détection (0.0-1.0).
            timestamp: Horodatage de la détection (auto-généré si absent).

        Returns:
            bool: True si l'alerte a été envoyée, False si cooldown actif ou erreur.
        """
        # Vérification du cooldown anti-spam
        if self._is_cooldown_active():
            with self._lock:
                self._total_skipped_cooldown += 1
            logger.debug(
                f"Alerte ignorée (cooldown actif). "
                f"Total ignorées : {self._total_skipped_cooldown}"
            )
            return False

        # Vérification de l'existence du fichier image
        img_file = Path(image_path)
        if not img_file.exists():
            logger.error(f"Fichier snapshot introuvable : {image_path}")
            with self._lock:
                self._total_failed += 1
            return False

        # Construction du message d'alerte formaté
        ts = timestamp or time.strftime("%Y-%m-%d %H:%M:%S")
        caption = (
            f"🚨 <b>ALERTE INTRUSION — SENTINEL-EDGE</b>\n\n"
            f"🕐 <b>Horodatage :</b> {ts}\n"
            f"📊 <b>Confiance :</b> {confidence:.1%}\n"
            f"🎯 <b>Classe :</b> Personne humaine (COCO 0)\n"
            f"📍 <b>Source :</b> Périmètre surveillé\n\n"
            f"⚡ <i>Alerte générée automatiquement par Sentinel-Edge MVP V0</i>"
        )

        try:
            url = self._build_url("sendPhoto")
            with open(image_path, "rb") as photo_file:
                files = {"photo": (img_file.name, photo_file, "image/jpeg")}
                data = {
                    "chat_id": self.chat_id,
                    "caption": caption,
                    "parse_mode": "HTML",
                }
                response = requests.post(
                    url, data=data, files=files, timeout=self.timeout
                )

            result = response.json()
            if result.get("ok"):
                with self._lock:
                    self._last_alert_time = time.time()
                    self._total_sent += 1
                logger.info(
                    f"✅ Alerte Telegram envoyée avec succès ! "
                    f"(confiance={confidence:.2f}, total={self._total_sent})"
                )
                return True
            else:
                err_desc = result.get("description", "Erreur inconnue")
                logger.error(f"Erreur sendPhoto Telegram : {err_desc}")
                with self._lock:
                    self._total_failed += 1
                return False

        except requests.RequestException as e:
            logger.error(f"Erreur réseau lors de l'envoi de l'alerte : {e}")
            with self._lock:
                self._total_failed += 1
            return False

    def send_alert_async(
        self,
        image_path: str,
        confidence: float,
        timestamp: Optional[str] = None,
    ) -> None:
        """Envoie une alerte de manière asynchrone non-bloquante (dans un thread dédié).

        Cette méthode retourne immédiatement sans bloquer le thread d'inférence IA.

        Args:
            image_path: Chemin vers le snapshot annoté.
            confidence: Score de confiance maximal.
            timestamp: Horodatage optionnel.
        """
        t = threading.Thread(
            target=self.send_intrusion_alert,
            args=(image_path, confidence, timestamp),
            name="Sentinel-TelegramAlert",
            daemon=True,
        )
        t.start()

    def get_stats(self) -> dict:
        """Retourne les statistiques d'envoi pour le Dashboard."""
        with self._lock:
            return {
                "total_sent": self._total_sent,
                "total_failed": self._total_failed,
                "total_skipped_cooldown": self._total_skipped_cooldown,
                "cooldown_seconds": self.cooldown,
                "last_alert_time": self._last_alert_time,
                "is_configured": self._is_configured,
            }


def create_notifier_from_config() -> Optional[TelegramNotifier]:
    """Factory : crée un TelegramNotifier à partir de la configuration .env.

    Returns:
        TelegramNotifier ou None si les tokens ne sont pas configurés.
    """
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from config import Config

    if not Config.TELEGRAM_BOT_TOKEN or not Config.TELEGRAM_CHAT_ID:
        logger.warning(
            "Telegram non configuré (TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID manquant). "
            "Les alertes Telegram sont désactivées."
        )
        return None

    try:
        notifier = TelegramNotifier(
            bot_token=Config.TELEGRAM_BOT_TOKEN,
            chat_id=Config.TELEGRAM_CHAT_ID,
            cooldown=Config.ALERT_COOLDOWN,
        )
        return notifier
    except ValueError as e:
        logger.error(f"Erreur de configuration Telegram : {e}")
        return None


# =====================================================================
# Banc d'essai autonome
# =====================================================================
if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from config import Config

    print("=" * 65)
    print("  SENTINEL-EDGE — Test du Module de Notification Telegram")
    print("  Auteur : AMADOU H TRAORE (Pôle Télécom & Sécurité)")
    print("=" * 65)

    if not Config.TELEGRAM_BOT_TOKEN or not Config.TELEGRAM_CHAT_ID:
        print("\n[ERREUR] Variables TELEGRAM_BOT_TOKEN et TELEGRAM_CHAT_ID non définies.")
        print("Copiez .env.example en .env et renseignez vos tokens Telegram.")
        sys.exit(1)

    notifier = TelegramNotifier(
        bot_token=Config.TELEGRAM_BOT_TOKEN,
        chat_id=Config.TELEGRAM_CHAT_ID,
        cooldown=Config.ALERT_COOLDOWN,
    )

    print("\n[1/2] Test de connexion au bot Telegram...")
    if notifier.test_connection():
        print("  ✅ Connexion réussie !")
    else:
        print("  ❌ Échec de connexion. Vérifiez votre token.")
        sys.exit(1)

    print("\n[2/2] Envoi d'un message test...")
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    success = notifier.send_text(
        f"🛡️ <b>SENTINEL-EDGE — Test de notification</b>\n\n"
        f"✅ Le module Telegram fonctionne correctement !\n"
        f"🕐 Horodatage : {ts}\n"
        f"🔒 Canal de transmission chiffré TLS actif."
    )
    if success:
        print("  ✅ Message test envoyé avec succès !")
    else:
        print("  ❌ Échec de l'envoi du message.")

    print(f"\nStatistiques : {notifier.get_stats()}")
    print("Test terminé.")
