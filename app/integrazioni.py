"""Integrazioni e correzioni al catalogo di wikiacqua.it.

Il database delle acque e' del cliente e noi lo leggiamo soltanto. Qui sopra
si mette uno strato nostro, un file JSON, che l'assistente e l'app leggono al
posto del database "nudo". Le regole sono pensate perche' il database abbia
sempre l'ultima parola: se il cliente sistema una scheda, il nostro ritocco
smette da solo di contare.

    integra   un valore mancante (null) viene riempito; se il database ne ha
              uno, vale quello del database
    correggi  un valore sbagliato viene sostituito solo finche' nel database
              c'e' ancora quello sbagliato (se_ancora)
    nuove     acque assenti dal database; se compare una scheda con lo stesso
              nome, la nostra viene scartata

Il file non e' mai scritto qui: lo genera genera_integrazioni.py.
"""
import json
import re
import unicodedata

CHIAVI_VALIDE = ("integra", "correggi", "nuove")


def _vuoto(v) -> bool:
    return v is None or str(v).strip().lower() in ("", "null")


def _uguale(a, b) -> bool:
    try:
        return abs(float(str(a).replace(",", ".")) - float(str(b).replace(",", "."))) < 1e-9
    except (TypeError, ValueError):
        return False


def _chiave(nome) -> str:
    """Stessa regola di chat._chiave: maiuscole, accenti, spazi e il
    prefisso 'Acqua' non contano."""
    t = unicodedata.normalize("NFKD", str(nome or "")).encode("ascii", "ignore")
    k = re.sub(r"[^A-Z0-9]", "", t.decode().upper())
    return k[5:] if k.startswith("ACQUA") and len(k) > 5 else k


def carica(percorso: str) -> dict:
    """Il file delle integrazioni, oppure {} se manca o non e' leggibile:
    senza, il catalogo resta quello del database."""
    if not percorso:
        return {}
    try:
        with open(percorso, encoding="utf-8") as f:
            dati = json.load(f)
    except (OSError, ValueError):
        return {}
    return dati if isinstance(dati, dict) else {}


def applica(grezzo: list, integ: dict):
    """(catalogo con le integrazioni, conteggi). Non modifica l'originale."""
    schede = [dict(x) for x in grezzo if isinstance(x, dict)]
    conteggi = {"integrati": 0, "corretti": 0, "nuove": 0}
    if not integ:
        return schede, conteggi
    per_id = {str(x.get("ID")): x for x in schede}

    def sezione(nome, tipo):
        v = integ.get(nome)
        return v if isinstance(v, tipo) else tipo()

    for id_, campi in sezione("integra", dict).items():
        s = per_id.get(str(id_))
        if s is None or not isinstance(campi, dict):
            continue
        for campo, valore in campi.items():
            if _vuoto(s.get(campo)) and not _vuoto(valore):
                s[campo] = valore
                conteggi["integrati"] += 1

    for c in sezione("correggi", list):
        if not isinstance(c, dict):
            continue
        s = per_id.get(str(c.get("id")))
        campo = c.get("campo")
        if s is not None and campo and _uguale(s.get(campo), c.get("se_ancora")):
            s[campo] = c.get("valore")
            conteggi["corretti"] += 1

    presenti = {_chiave(x.get("NOME_ETICHETTA")) for x in schede}
    for n in sezione("nuove", list):
        if not isinstance(n, dict) or not n.get("NOME_ETICHETTA"):
            continue
        if _chiave(n["NOME_ETICHETTA"]) in presenti or str(n.get("ID")) in per_id:
            continue
        schede.append(dict(n))
        per_id[str(n.get("ID"))] = schede[-1]
        presenti.add(_chiave(n["NOME_ETICHETTA"]))
        conteggi["nuove"] += 1
    return schede, conteggi
