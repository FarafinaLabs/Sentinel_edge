#!/bin/bash
# Script de lancement du Dashboard d'Ingestion Sentinel-Edge
# Auteur : AMADOU H TRAORE (Pôle IA)

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "================================================================"
echo "  🛡️  SENTINEL-EDGE — PIPELINE D'INGESTION VIDÉO (MVP V0)"
echo "  Auteur : AMADOU H TRAORE (Pôle IA & Traitement de Données)"
echo "================================================================"

# Détection de l'interpréteur Python
if [ -f "../.venv/bin/python" ]; then
    PYTHON_EXEC="../.venv/bin/python"
elif [ -f ".venv/bin/python" ]; then
    PYTHON_EXEC=".venv/bin/python"
else
    PYTHON_EXEC="python3"
fi

echo "[+] Utilisation de l'interpréteur : $($PYTHON_EXEC --version)"

# Création du dossier captures s'il n'existe pas
mkdir -p captures

echo "[+] Démarrage du serveur Web Dashboard..."
exec $PYTHON_EXEC web/app.py
