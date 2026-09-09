# 🛡️ Sentinel-Edge (SafeHome Africa) — MVP V0

Système d'alerte et de vision intelligente locale (Edge AI) conçu pour les contraintes d'infrastructure locales.

## 🚀 Fonctionnalités du MVP
- **Capture Vidéo Découplée :** Supporte smartphone Android (IP Webcam) ou webcam interne.
- **Inférence IA Locale :** Détection humaine via YOLOv8n (CPU/GPU local).
- **Anti-Faux Positifs :** Persistance temporelle de détection et filtrage de confiance.
- **Alertes Téléphone :** Transmission instantanée et asynchrone des photos d'intrusion via Telegram.
- **Journalisation Locale :** Persistance des événements sous SQLite.

## 📦 Installation Rapide

1. Cloner le dépôt et entrer dans le dossier :
```bash
git clone git@github.com:Tomota113/sentinel-edge.git
cd sentinel-edge
```

2. Créer et activer l'environnement virtuel :
```bash
python3 -m venv venv
source venv/bin/activate
```

3. Installer les dépendances :
```bash
pip install -r requirements.txt
```

4. Configurer les variables d'environnement :
Copier `.env.example` en `.env` et renseigner les paramètres du flux vidéo et de Telegram :
```bash
cp .env.example .env
```

5. Démarrer le banc d'essai autonome du détecteur :
```bash
python3 core/detector.py 0
```
