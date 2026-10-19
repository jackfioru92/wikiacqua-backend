#!/usr/bin/env bash
# Collega il servizio di riserva dell'assistente (si usa quando Google non risponde).
#   bash imposta_riserva.sh [deepseek|mistral]      (predefinito: deepseek)
# La chiave la digiti tu: non si vede, non resta nella cronologia, non passa dalla chat
# e viene scritta solo in /etc/wikiacqua-ai/chat.env sul server (permessi 600).
# Prima di salvarla la prova con una chiamata vera: se non va, non cambia nulla.
set -euo pipefail
HOST=debian@57.131.42.4
FORNITORE="${1:-deepseek}"
case "$FORNITORE" in
  deepseek) URL="https://api.deepseek.com/chat/completions"; MODELLO="deepseek-chat" ;;
  mistral)  URL="https://api.mistral.ai/v1/chat/completions"; MODELLO="mistral-small-latest" ;;
  *) echo "Fornitore sconosciuto: $FORNITORE (deepseek o mistral)"; exit 1 ;;
esac
read -r -s -p "Chiave API di $FORNITORE: " KEY; echo
[ -n "$KEY" ] || { echo "Chiave vuota."; exit 1; }

# Lo script remoto legge la chiave dallo standard input: non compare tra gli argomenti dei processi.
SCRIPT=$(cat <<PY
import json, os, sys, urllib.request, urllib.error
k = sys.stdin.read().strip()
URL, MODELLO = "$URL", "$MODELLO"
req = urllib.request.Request(URL, data=json.dumps({"model": MODELLO, "max_tokens": 5,
    "messages": [{"role": "user", "content": "ciao"}]}).encode(),
    headers={"Authorization": "Bearer " + k, "Content-Type": "application/json"})
try:
    r = urllib.request.urlopen(req, timeout=30)
    print("prova del servizio: HTTP", r.status, "- risponde")
except urllib.error.HTTPError as e:
    print("prova del servizio: HTTP", e.code, "- chiave non valida o credito esaurito: non salvo nulla")
    sys.exit(2)
except Exception as e:
    print("prova del servizio non riuscita:", type(e).__name__, "- non salvo nulla")
    sys.exit(3)
p = "/etc/wikiacqua-ai/chat.env"
tieni = [l for l in open(p).read().splitlines()
         if not l.startswith(("LLM_RISERVA_KEY=", "LLM_RISERVA_URL=", "LLM_RISERVA_MODELLO="))]
tieni += ["LLM_RISERVA_KEY=" + k, "LLM_RISERVA_URL=" + URL, "LLM_RISERVA_MODELLO=" + MODELLO]
open(p, "w").write("\n".join(tieni) + "\n")
os.chmod(p, 0o600)
print("salvata in", p)
PY
)
printf '%s' "$KEY" | ssh -o BatchMode=yes "$HOST" "sudo python3 -c '$SCRIPT'"
unset KEY
ssh -o BatchMode=yes "$HOST" 'sudo systemctl restart wikiacqua-ai; sleep 4; systemctl is-active wikiacqua-ai; curl -sS -m 10 http://127.0.0.1:8002/chat/stato | python3 -c "import sys,json; print(\"motori in ordine:\", json.load(sys.stdin)[\"motori\"])"'
echo; echo "Fatto: se Google non risponde, l'assistente passa da solo al servizio di riserva."
