# WikiAcqua · backend dell'assistente

FastAPI sul VPS `wikideas.it` (servizio `wikiacqua-ai`, porta 8002, nginx su `/wikiacqua/ai/`).

- `app/chat.py` assistente (`POST /chat`), definizioni dall'Enciclopedia, `GET /catalogo`
- `app/integrazioni.py` strato nostro sopra il database di wikiacqua.it (che è del cliente, sola lettura)
- `app/main.py` riconoscimento etichette da foto; `main.py.server` è l'originale prima delle 3 righe che includono `chat`
- `data/integrazioni.json` valori integrati, correzioni e acque nuove (ID da 90001), generato da `genera_integrazioni.py`

## Prove
```
python3 -m venv venv && venv/bin/pip install -r requirements-dev.txt
venv/bin/python -m pytest -q
```

## Aggiornare le acque
`python3 genera_integrazioni.py Acque_dati_integrati_WikiAcqua.xlsx`, poi copiare `data/integrazioni.json`
in `/opt/wikiacqua-ai/catalogo/integrazioni.json`. Si rilegge da solo entro 5 minuti, senza riavvii.

## Pubblicare
Copiare `app/chat.py` e `app/integrazioni.py` in `/opt/wikiacqua-ai/app/` e `sudo systemctl restart wikiacqua-ai`.
Prima salvare `chat.py` come `chat.py.bak-AAAAMMGG`. Il token del database sta in `/etc/wikiacqua-ai/chat.env`
(non è nel repo, e non deve entrarci).

## Se Google non risponde
`_gemini` prova i motori in ordine: modello principale, riserve Google (`GEMINI_MODELLI_RISERVA`, stessa chiave),
poi un servizio esterno compatibile OpenAI (`LLM_RISERVA_KEY`, `LLM_RISERVA_URL`, `LLM_RISERVA_MODELLO`).
Chi non risponde scende in fondo alla fila per 45 secondi. `bash imposta_riserva.sh [deepseek|mistral]` salva la
chiave sul server (la chiede nascosta, la prova prima di salvarla). Lo stato: `curl 127.0.0.1:8002/chat/stato`.
I registri sono in `/opt/wikiacqua-ai/logs/app.log` (non in journalctl).
