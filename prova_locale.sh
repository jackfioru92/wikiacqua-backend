#!/usr/bin/env bash
# Avvia il backend in locale con Gemini vero, sulla porta 8002.
# La chiave la digiti tu a richiesta (non appare e non viene salvata).
# Usa una chiave di SVILUPPO: se ne crea una gratis su aistudio.google.com.
cd "$(dirname "$0")" || exit 1
read -r -s -p "Chiave Gemini di sviluppo: " GEMINI_API_KEY; echo
export GEMINI_API_KEY DB_ACQUE_FILE="$PWD/fixtures/catalogo.json"
exec ./venv/bin/python -m uvicorn --app-dir app main:app --host 127.0.0.1 --port 8002
