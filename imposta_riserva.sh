#!/usr/bin/env bash
# Collega un servizio di riserva dell'assistente (si usa quando Google non risponde).
#   bash imposta_riserva.sh groq|cerebras|mistral|deepseek
# Gratuiti (provati per primi): groq, cerebras, mistral. A pagamento (per ultimo): deepseek.
# La chiave la digiti tu: non si vede, non resta nella cronologia, non passa dalla chat
# e viene scritta solo in /etc/wikiacqua-ai/chat.env sul server (permessi 600).
# Prima di salvarla la prova con una chiamata vera, in modalita' JSON come fa l'assistente:
# se non va, non cambia nulla.
set -euo pipefail
HOST=debian@57.131.42.4
FORNITORE="${1:-}"
FORZATO="${2:-}"      # facoltativo: bash imposta_riserva.sh groq nome-del-modello
case "$FORNITORE" in
  groq)     SLOT=2;  BASE="https://api.groq.com/openai/v1";  PREDEFINITO="llama-3.3-70b-versatile" ;;
  cerebras) SLOT=3;  BASE="https://api.cerebras.ai/v1";      PREDEFINITO="llama-3.3-70b" ;;
  mistral)  SLOT=4;  BASE="https://api.mistral.ai/v1";       PREDEFINITO="mistral-small-latest" ;;
  deepseek) SLOT="";  BASE="https://api.deepseek.com/v1";    PREDEFINITO="deepseek-chat" ;;
  *) echo "Uso: bash imposta_riserva.sh groq|cerebras|mistral|deepseek [modello]"; exit 1 ;;
esac
read -r -s -p "Chiave API di $FORNITORE: " KEY; echo
[ -n "$KEY" ] || { echo "Chiave vuota."; exit 1; }

# Lo script remoto legge la chiave dallo standard input: non compare tra gli argomenti dei processi.
SCRIPT=$(cat <<PY
import json, os, sys, urllib.request, urllib.error
k = sys.stdin.read().strip()
BASE, PRED, SLOT, FORN, FORZ = "$BASE", "$PREDEFINITO", "$SLOT", "$FORNITORE", "$FORZATO"
URL = BASE + "/chat/completions"
def chiama(url, corpo=None):
    req = urllib.request.Request(url, data=json.dumps(corpo).encode() if corpo else None,
        headers={"Authorization": "Bearer " + k, "Content-Type": "application/json", "User-Agent": "wikiacqua-ai"})
    return json.load(urllib.request.urlopen(req, timeout=40))
# 1. quali modelli ha. Si saltano quelli di sicurezza, audio ed embedding
ESCLUDI = ("guard", "whisper", "tts", "embed", "orpheus", "playai", "safeguard", "moderation", "transcribe", "image", "ocr")
PREFERITI = ("llama-3.3-70b", "gpt-oss-120b", "llama-4-maverick", "llama-4-scout", "qwen", "70b", "120b", "32b", "kimi", "gpt-oss-20b", "8b")
try:
    ids = [m["id"] for m in chiama(BASE + "/models").get("data", [])]
except Exception as e:
    ids = []
    print("elenco modelli non disponibile (" + type(e).__name__ + ")")
chat = [i for i in ids if not any(x in i.lower() for x in ESCLUDI)]
if FORZ:
    candidati = [FORZ]
elif PRED in ids or not chat:
    candidati = [PRED]
else:
    candidati = []
    for pref in PREFERITI:
        for i in chat:
            if pref in i.lower() and i not in candidati:
                candidati.append(i)
    candidati += [i for i in chat if i not in candidati]
    candidati = candidati[:4]
    print("modello predefinito non disponibile. Modelli di chat trovati:", ", ".join(chat[:25]))
# 2. prova vera, in modalita JSON come fa l assistente, fino a trovare un modello che va
def extra_per(m):
    # i modelli che ragionano consumano i token pensando: si chiede poco ragionamento
    return {"reasoning_effort": "low"} if "gpt-oss" in m.lower() else {}
ok = None
for modello in candidati:
    extra = extra_per(modello)
    corpo = {"model": modello, "max_tokens": 400, "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": "Rispondi solo con un oggetto JSON."},
                     {"role": "user", "content": "Rispondi con {\"ok\": true}"}]}
    corpo.update(extra)
    try:
        r = chiama(URL, corpo)
        scelta = r["choices"][0]
        if scelta.get("finish_reason") == "length":
            raise ValueError("risposta troncata")
        json.loads(scelta["message"]["content"])
        ok = (modello, extra)
        print("prova del servizio: " + modello + " risponde in JSON")
        break
    except urllib.error.HTTPError as e:
        try:
            dett = json.loads(e.read().decode()).get("error", {})
            dett = dett.get("message") if isinstance(dett, dict) else str(dett)
        except Exception:
            dett = "-"
        print("provato " + modello + ": HTTP", e.code, "-", str(dett)[:150])
        if e.code in (401, 403):
            break
    except Exception as e:
        print("provato " + modello + ":", type(e).__name__, str(e)[:100])
if not ok:
    print("nessun modello ha funzionato. Chiave lunga", len(k), "caratteri, comincia per", k[:4] + "...")
    print("non salvo nulla")
    sys.exit(2)
modello, extra = ok
# 3. si salva nello slot del fornitore, senza toccare gli altri
p = "/etc/wikiacqua-ai/chat.env"
pref = "LLM_RISERVA" + SLOT + "_"
tieni = [l for l in open(p).read().splitlines() if not l.startswith((pref + "KEY=", pref + "URL=", pref + "MODELLO=", pref + "EXTRA="))]
tieni += [pref + "KEY=" + k, pref + "URL=" + URL, pref + "MODELLO=" + modello]
if extra:
    tieni.append(pref + "EXTRA=" + json.dumps(extra))
open(p, "w").write("\n".join(tieni) + "\n")
os.chmod(p, 0o600)
print("salvato in", p, "(slot", SLOT or "senza numero" + ")")
PY
)
printf '%s' "$KEY" | ssh -o BatchMode=yes "$HOST" "sudo python3 -c '$SCRIPT'"
unset KEY
ssh -o BatchMode=yes "$HOST" 'sudo systemctl restart wikiacqua-ai; sleep 4; systemctl is-active wikiacqua-ai; curl -sS -m 10 http://127.0.0.1:8002/chat/stato | python3 -c "import sys,json; print(\"motori in ordine:\", json.load(sys.stdin)[\"motori\"])"'
echo; echo "Fatto: se Google non risponde, l'assistente prova anche $FORNITORE."
