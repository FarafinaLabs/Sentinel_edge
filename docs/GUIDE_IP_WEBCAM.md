# 📱 GUIDE TECHNIQUE : CONFIGURATION D'UN SMARTPHONE COMME CAMÉRA IP (0 F CFA)

Ce guide détaille la mise en place d'une caméra de sécurité sans fil à l'aide d'un simple smartphone Android pour alimenter le pipeline d'ingestion de **Sentinel-Edge**.

---

## 1. Pourquoi IP Webcam ?

Pour respecter la contrainte du MVP à **0 F CFA** et pallier le coût prohibitif des caméras IP industrielles (300 000 à 800 000 F CFA), nous transformons les smartphones de l'équipe en caméras réseau haute définition via le protocole standard MJPEG / HTTP.

---

## 2. Étapes de Configuration Pas à Pas

### Étape 1 : Installation
1. Ouvrez le **Google Play Store** (ou téléchargez l'APK sur F-Droid / GitHub).
2. Recherchez : **IP Webcam** (éditeur : Pavel Khlebovich).
3. Installez l'application (légère, moins de 15 Mo).

### Étape 2 : Réseau Local
Assurez-vous que le PC hébergeant Sentinel-Edge et votre smartphone sont sur le même réseau :
- **Option A (Recommandée) :** Tous deux connectés sur la même box Wi-Fi locale.
- **Option B (Terrain / Hors box) :** Activez le **Partage de connexion Wi-Fi (Point d'accès mobile)** sur le smartphone et connectez votre PC au réseau du téléphone. *Aucune consommation de données mobiles Internet n'est requise : la communication vidéo reste 100 % locale (LAN).*

### Étape 3 : Réglages Vidéo Optimaux dans l'application
Avant de lancer le flux, ajustez les options pour maximiser l'autonomie et limiter la chauffe :
- **Préférences vidéo** :
  - *Résolution de la vidéo* : Choisissez **640x480** ou **1280x720** (évitez 1080p/4K qui sature inutilement le CPU et la batterie).
  - *Qualité* : Réglez entre **50 % et 75 %**.
  - *Orientation* : Paysage (horizontal).
- **Gestion de l'alimentation** :
  - Activez l'option *Empêcher la mise en veille de l'écran*.

### Étape 4 : Lancement du Serveur Vidéo
1. Descendez tout en bas du menu principal de l'application.
2. Touchez **"Démarrer le serveur"** (Start server).
3. L'appareil photo s'active et affiche une adresse réseau au bas de l'écran :
   ```text
   http://192.168.1.45:8080
   ```
   *(Notez bien les 4 chiffres de l'adresse IP spécifique à votre réseau).*

---

## 3. Connexion dans Sentinel-Edge

Dans le tableau de bord web de Sentinel-Edge (`http://localhost:5000`) :
1. Dans le champ **URL Smartphone (IP Webcam / RTSP)**, saisissez :
   ```text
   http://192.168.1.45:8080/video
   ```
   *(Pensez à bien ajouter `/video` à la fin de l'URL pour pointer sur le flux vidéo direct).*
2. Cliquez sur **Connecter**.
3. Le flux en direct de votre smartphone s'affiche instantanément sur votre écran d'ordinateur avec la télémétrie FPS !

---

## 4. Astuces & Dépannage

- **L'image ne charge pas ?**
  - Vérifiez que le PC peut joindre le smartphone en ouvrant un terminal et en lançant :
    ```bash
    ping -c 3 192.168.1.45
    ```
  - Testez l'ouverture de `http://192.168.1.45:8080` dans votre navigateur web.
- **Le flux se déconnecte au bout de 10 minutes ?**
  - Sur Android, désactivez l'optimisation de batterie pour l'application *IP Webcam* dans les paramètres du téléphone afin qu'Android ne la tue pas en arrière-plan.
