# WikiAcqua · backend dell'assistente

FastAPI sul VPS `wikideas.it` (servizio `wikiacqua-ai`, porta 8002, nginx su `/wikiacqua/ai/`, 2 worker).
L'app è in `jackfioru92/wikiacqua-app`.

## Cosa fa
- `POST /chat` l'assistente. Un'IA traduce la domanda in un piano (filtri, acque, categoria), la ricerca e i
  confronti li fa Python sul catalogo, un'IA scrive la risposta e ogni numero viene controllato: se non
  viene dai dati, si risponde con la tabella. Domande estranee alle acque: rifiuto fisso, senza costi.
- `GET /catalogo` il catalogo per l'app: database di wikiacqua.it più il nostro strato.
- Le definizioni ("cos'è il residuo fisso?") si leggono dall'Enciclopedia del database, senza IA.
- `POST /` riconoscimento delle etichette da foto (codice preesistente in `app/main.py`; `main.py.server` è
  l'originale prima delle 3 righe che includono `chat`).

## File
- `app/chat.py` l'assistente · `app/integrazioni.py` lo strato sul database del cliente
- `data/integrazioni.json` valori integrati, correzioni e acque nuove (ID da 90001), generato da
  `genera_integrazioni.py` partendo dal foglio delle acque. Regola: il database vince sempre (si riempie solo
  ciò che è vuoto, si corregge solo finché il database ha ancora il valore sbagliato).
- `tests/` 216 test, `fixtures/` copie del catalogo e dell'Enciclopedia per le prove

## Se Google non risponde
Si provano in ordine: modello principale, due riserve Google (`GEMINI_MODELLI_RISERVA`, stessa chiave), poi i
servizi esterni compatibili OpenAI, uno per "slot" in `/etc/wikiacqua-ai/chat.env` (`LLM_RISERVA<n>_KEY`, `_URL`,
`_MODELLO`): prima i gratuiti (slot 2 Groq, 3 Cerebras, 4 Mistral), per ultimo DeepSeek (a pagamento, slot senza
numero), così il credito si consuma solo se serve. Chi non risponde scende in fondo alla fila per 45 secondi.
Per aggiungerne uno: `bash imposta_riserva.sh groq|cerebras|mistral|deepseek` (chiede la chiave nascosta, la
prova in modalità JSON, salva solo se funziona e riavvia). Stato e motori: `curl 127.0.0.1:8002/chat/stato`.
Oggi sono attivi Google (3 modelli) e DeepSeek. Limiti: 40 domande al giorno per rete, 2.000 in totale.

## Prove
```
python3 -m venv venv && venv/bin/pip install -r requirements-dev.txt
venv/bin/python -m pytest -q
```

## Aggiornare le acque
`python3 genera_integrazioni.py Acque_dati_integrati_WikiAcqua.xlsx`, poi copiare `data/integrazioni.json` in
`/opt/wikiacqua-ai/catalogo/integrazioni.json`. Il server lo rilegge da solo entro 5 minuti, senza riavvii.
Le correzioni stanno nella lista `CORREZIONI` dello script, con il valore sbagliato che devono trovare.

## Pubblicare
1. Prove locali verdi.
2. Salvare `/opt/wikiacqua-ai/app/chat.py` come `chat.py.bak-AAAAMMGG`, copiare `app/chat.py` e
   `app/integrazioni.py` in `/opt/wikiacqua-ai/app/`, poi `sudo systemctl restart wikiacqua-ai`.
3. Controllare `curl 127.0.0.1:8002/health` e `curl 127.0.0.1:8002/chat/stato` (motori, consumi).
Rientro: rimettere il `.bak` e riavviare.

## Dove sono i segreti (non sono nel repo e non devono entrarci)
- `/etc/wikiacqua-ai/api_keys.env` chiave Google · `/etc/wikiacqua-ai/chat.env` token del database e chiave
  del servizio di riserva (permessi 600).
- I registri sono in `/opt/wikiacqua-ai/logs/app.log` e `error.log`, non in `journalctl`.
