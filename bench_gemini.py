#!/usr/bin/env python3
"""Misura la velocita' reale di Gemini per le due chiamate dell'assistente.
Chiede la chiave dall'ambiente (GEMINI_API_KEY).

    GEMINI_API_KEY=... python3 bench_gemini.py [giri]
"""
import asyncio, json, os, statistics as st, sys, time

QUI = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("DB_ACQUE_FILE", os.path.join(QUI, "fixtures", "catalogo.json"))
sys.path.insert(0, os.path.join(QUI, "app"))
import chat

GIRI = int(sys.argv[1]) if len(sys.argv) > 1 else 5
DOMANDE = ["Qual e' la differenza in termini di calcio tra Ferrarelle e Levissima?",
           "Ho la pressione alta, quale acqua ha meno sodio?",
           "Quale acqua e' adatta a un neonato di sei mesi?",
           "Confronta Ferrarelle, Levissima e Sant'Anna",
           "Acque dell'Umbria con poco sodio"]


async def misura(variante, tipo, i, schede):
    prima = (chat._uso["token_in"], chat._uso["token_out"])
    t = time.time()
    try:
        if tipo == "piano":
            await chat._gemini("Domanda: " + DOMANDE[i % len(DOMANDE)], sistema=chat.SISTEMA_PIANO,
                               schema=chat.SCHEMA_PIANO, max_token=512, temperatura=0)
        else:
            piano = chat._piano_valido({"azione": "confronta", "acque": ["Ferrarelle", "Levissima", "Sant'Anna"]})
            ris = chat.esegui(piano, schede)
            await chat._gemini("DATI:\n" + json.dumps(chat._dati(piano, ris), ensure_ascii=False),
                               sistema=chat.SISTEMA_RISPOSTA, max_token=800, temperatura=0.3)
        err = None
    except chat.GeminiErrore as e:
        err = str(e)
    return time.time() - t, err, chat._uso["token_out"] - prima[1]


async def main():
    schede = await chat.catalogo()
    ris = {}
    for giro in range(GIRI):
        varianti = [""]
        for v in varianti:
            for tipo in ("piano", "testo"):
                sec, err, tok = await misura(v, tipo, giro, schede)
                ris.setdefault((v or "predefinito", tipo), []).append((sec, err, tok))
                print(f"  giro {giro+1} {v or 'predefinito':<12} {tipo:<6} {sec:5.1f}s  {('ERRORE ' + err) if err else 'ok'}", flush=True)
                await asyncio.sleep(4)
    print("\n" + "=" * 72)
    print(f"{'ragionamento':<14}{'chiamata':<8}{'ok':>4}{'mediana':>9}{'massimo':>9}{'token usc.':>12}")
    for (v, tipo), r in sorted(ris.items()):
        buone = [x for x in r if not x[1]]
        if buone:
            print(f"{v:<14}{tipo:<8}{len(buone):>2}/{len(r):<2}{st.median(x[0] for x in buone):8.1f}s{max(x[0] for x in buone):8.1f}s"
                  f"{st.mean(x[2] for x in buone):12.0f}")
        else:
            print(f"{v:<14}{tipo:<8} 0/{len(r)}  tutti falliti: {r[0][1]}")

asyncio.run(main())
