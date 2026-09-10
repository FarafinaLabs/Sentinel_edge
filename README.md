# 🛡️ Sentinel-Edge (SafeHome Africa) — MVP V0

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![YOLOv8](https://img.shields.io/badge/Inference-YOLOv8n%20CPU-brightgreen.svg)](https://docs.ultralytics.com/)
[![OpenCV](https://img.shields.io/badge/Vision-OpenCV%204.8%2B-5C3EE8.svg)](https://opencv.org/)
[![Database](https://img.shields.io/badge/Storage-SQLite3-003B57.svg)](https://www.sqlite.org/)
[![Organization](https://img.shields.io/badge/Lab-FarafinaLabs-orange.svg)](https://github.com/FarafinaLabs)
[![Budget](https://img.shields.io/badge/MVP%20Budget-0%20F%20CFA-success.svg)](#)

> **Système d'alerte et de vision intelligente locale (Edge AI) conçu pour les contraintes d'infrastructure locales en Afrique.**  
> Détection d'intrusion humaine en temps réel, filtrage anti-faux positifs et transmission instantanée d'alertes sans dépendance cloud.

---

## 📌 Présentation du Projet

Dans de nombreuses régions, l'accès à une connexion Internet permanente et à haut débit est instable, et les coupures de courant sont récurrentes. Les solutions de surveillance classiques dépendantes du Cloud deviennent inopérantes dès la perte de connectivité.

**Sentinel-Edge** répond à ce défi en déportant l'intelligence artificielle directement à la périphérie (**Edge AI**) :
- **Budget MVP 0 F CFA :** Fonctionne sans investissement matériel initial, en exploitant les équipements existants (ordinateurs portables Ubuntu, smartphones Android en caméras IP et simulateurs logiciels).
- **Inférence Locale :** Analyse visuelle en temps réel sur processeur standard (CPU x86 ou ARM) grâce à **Ultralytics YOLOv8n**.
- **Anti-Faux Positifs :** Algorithme de persistance temporelle éliminant les bruits optiques (ombres, animaux, insectes, variations d'éclairage).
- **Alerte Instantanée :** Notification chiffrée avec cliché annoté envoyée sur un canal Telegram dédié dès confirmation de l'intrusion.
- **Journalisation Locale :** Sauvegarde persistante des métadonnées dans une base SQLite locale.

---

## 📚 Documentation Officielle du Projet

Pour une compréhension exhaustive du projet, consultez les documents de référence inclus dans ce dépôt :

| Document | Description |
| :--- | :--- |
| 📄 [**CAHIER_DES_CHARGES.md**](CAHIER_DES_CHARGES.md) | **Cahier des charges officiel :** objectifs, spécifications fonctionnelles, matrice d'évolution MVP $\rightarrow$ V1, planning sur 4 semaines et critères d'acceptation. |
| 🛠️ [**DOSSIER_TECHNIQUE.md**](DOSSIER_TECHNIQUE.md) | **Dossier technique de génie logiciel :** architecture multithreadée à 4 niveaux, gestion de flux sans latence (*drop oldest*), workflow Trello et nomenclature matérielle chiffrée en Francs CFA (Bamako). |
| 📘 [**EXPLICATION_CODE.md**](EXPLICATION_CODE.md) | **Guide d'explication du code :** analyse ligne par ligne de la classe `IntrusionDetector`, optimisation CPU (`classes=[0]`), automate temporel et banc d'essai autonome. |

---

## 🏛️ Architecture Logicielle Découplée

Afin d'éviter tout ralentissement de l'acquisition vidéo par les calculs d'inférence ou les latences réseau, le système est segmenté en **4 threads indépendants** :

```text
┌─────────────────────────────────┐
│ Thread 1 : VideoCapture (RTSP)  │  <-- Smartphone Android / Webcam
└────────────────┬────────────────┘
                 │ FrameQueue (maxsize=2, drop oldest)
                 ▼
┌─────────────────────────────────┐
│ Thread 2 : Inference & Logique   │  <-- YOLOv8n (CPU) + Persistance >= 2 frames
└────────┬────────────────────────┘
         │
         ├───────────────────────────────┐
         ▼                               ▼
┌─────────────────────────────────┐   ┌─────────────────────────────────┐
│ Thread 3 : Async Telegram Alert │   │ Thread 4 : SQLite Local Logger  │
└─────────────────────────────────┘   └─────────────────────────────────┘
```

---

## 🚀 Démarrage Rapide

### 1. Cloner le dépôt
```bash
git clone git@github.com:FarafinaLabs/Sentinel_edge.git
cd Sentinel_edge
```

### 2. Créer et activer l'environnement virtuel
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Installer les dépendances
```bash
pip install -r requirements.txt
```

### 4. Lancer le banc d'essai autonome du détecteur
Le fichier [`core/detector.py`](core/detector.py) intègre un banc de test autonome avec affichage du statut en temps réel et calcul de FPS lissé :

```bash
# Test sur la webcam locale intégrée (source 0)
python3 core/detector.py 0

# Test sur un flux vidéo ou smartphone IP Webcam
python3 core/detector.py "http://192.168.1.50:8080/video"
```

**Commandes interactives du banc d'essai :**
- `q` ou `Echap` : Quitter l'application et libérer proprement les ressources vidéo.
- `r` : Réinitialiser manuellement le compteur de détection temporelle.

---

## 🧱 Structure du Dépôt

```text
sentinel-edge/
├── .gitignore              # Règles d'exclusion Git (caches, .pt, captures, db)
├── README.md               # Présentation et guide de démarrage
├── CAHIER_DES_CHARGES.md   # Spécifications fonctionnelles et jalons du MVP
├── DOSSIER_TECHNIQUE.md    # Architecture multithreadée et nomenclature matérielle
├── EXPLICATION_CODE.md     # Analyse détaillée du code source
├── config.py               # Paramètres globaux et seuils configurables
├── requirements.txt        # Dépendances Python requises
└── core/
    ├── __init__.py         # Export du package core
    └── detector.py         # Classe IntrusionDetector avec persistance temporelle
```

---

## 🗺️ Roadmap du Sprint (MVP 1 Mois)

- [x] **Semaine 1 :** Ingestion vidéo fluide, banc d'essai webcam & architecture modulaire.
- [x] **Semaine 2 :** Intégration de YOLOv8n, filtrage classe `person`, persistance temporelle anti-faux positifs et documentation complète.
- [ ] **Semaine 3 :** Finalisation de l'orchestrateur `app.py`, journalisation SQLite et schéma d'alimentation KiCAD.
- [ ] **Semaine 4 :** Test d'endurance de 2h en continu, validation de la latence (< 2s) et démonstration en direct.

---

## 💡 Évolution Matérielle V1 (Projection Bamako)

Le passage à la version physique embarquée (Raspberry Pi 4 + Pi Camera Module + Relais + Batterie Li-Ion de secours) est estimé entre **55 500 et 75 000 F CFA**. Tous les détails de la nomenclature sont documentés dans le [Dossier Technique](DOSSIER_TECHNIQUE.md#4-nomenclature--projection-budgétaire-pour-le-pôle-électronique).

---

## 👥 Équipe & Organisation

Projet développé au sein de **FarafinaLabs**.  
Développé dans le cadre du projet **Sentinel-Edge (SafeHome Africa)**.
