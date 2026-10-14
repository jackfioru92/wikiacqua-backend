"""Lo strato nostro sopra il database di wikiacqua.it (integrazioni.py)."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import chat
import integrazioni
import main

CATALOGO = json.load(open(Path(__file__).parent.parent / "fixtures" / "catalogo.json", encoding="utf-8"))


@pytest.fixture(autouse=True)
def pulito(monkeypatch):
    monkeypatch.setattr(chat, "CACHE_ATTIVA", False)
    chat._risposte.svuota()
    chat._testi.svuota()
    chat._cache.update(schede=[], grezzo=[], letto=0.0, impronta="", integrazioni={})
    yield


def _con_nitrati_vuoti():
    return next(x for x in CATALOGO if x["NITRATI"] in (None, ""))


def _con_nitrati():
    return next(x for x in CATALOGO if x["NITRATI"] not in (None, ""))


NUOVA = {k: None for k in CATALOGO[0]} | {
    "ID": 90001, "NOME_ETICHETTA": "FONTE DEL TEST", "REGIONE": "Lazio",
    "CLASSIFICAZIONE": "Oligominerale", "RESIDUO_FISSO_A_180": "100.00",
    "SODIO": "5.00", "CALCIO": "20.00", "MAGNESIO": "3.00", "NITRATI": "2.00"}


def test_il_database_non_viene_modificato():
    prima = json.dumps(CATALOGO, sort_keys=True)
    integrazioni.applica(CATALOGO, {"integra": {str(_con_nitrati_vuoti()["ID"]): {"NITRATI": "9.00"}}})
    assert json.dumps(CATALOGO, sort_keys=True) == prima


def test_integra_riempie_solo_i_vuoti():
    vuota, piena = _con_nitrati_vuoti(), _con_nitrati()
    out, n = integrazioni.applica(CATALOGO, {"integra": {
        str(vuota["ID"]): {"NITRATI": "7.00"}, str(piena["ID"]): {"NITRATI": "99.00"}}})
    per_id = {str(x["ID"]): x for x in out}
    assert per_id[str(vuota["ID"])]["NITRATI"] == "7.00"
    assert per_id[str(piena["ID"])]["NITRATI"] == piena["NITRATI"]     # il database vince
    assert n["integrati"] == 1


def test_correggi_vale_solo_finche_il_database_e_sbagliato():
    s = _con_nitrati()
    regola = {"id": str(s["ID"]), "campo": "NITRATI", "se_ancora": s["NITRATI"], "valore": 1.5}
    out, n = integrazioni.applica(CATALOGO, {"correggi": [regola]})
    assert {str(x["ID"]): x for x in out}[str(s["ID"])]["NITRATI"] == 1.5 and n["corretti"] == 1
    # il cliente ha sistemato la scheda per conto suo: la nostra correzione non conta piu'
    sistemata = [dict(x, NITRATI="3.20") if x["ID"] == s["ID"] else x for x in CATALOGO]
    out, n = integrazioni.applica(sistemata, {"correggi": [regola]})
    assert {str(x["ID"]): x for x in out}[str(s["ID"])]["NITRATI"] == "3.20" and n["corretti"] == 0


def test_correggi_confronta_i_numeri_non_il_testo():
    s = _con_nitrati()
    regola = {"id": str(s["ID"]), "campo": "NITRATI", "se_ancora": float(s["NITRATI"]), "valore": 1}
    assert integrazioni.applica(CATALOGO, {"correggi": [regola]})[1]["corretti"] == 1


def test_nuove_si_aggiungono_e_il_database_ha_la_precedenza():
    out, n = integrazioni.applica(CATALOGO, {"nuove": [NUOVA]})
    assert len(out) == len(CATALOGO) + 1 and n["nuove"] == 1
    gia = dict(NUOVA, NOME_ETICHETTA=CATALOGO[0]["NOME_ETICHETTA"].lower(), ID=90002)
    assert integrazioni.applica(CATALOGO, {"nuove": [gia]})[1]["nuove"] == 0      # stesso nome
    assert integrazioni.applica(CATALOGO, {"nuove": [dict(NUOVA, ID=CATALOGO[0]["ID"])]})[1]["nuove"] == 0


def test_applicarle_due_volte_da_lo_stesso_risultato():
    integ = {"integra": {str(_con_nitrati_vuoti()["ID"]): {"NITRATI": "7.00"}}, "nuove": [NUOVA]}
    una, _ = integrazioni.applica(CATALOGO, integ)
    due, _ = integrazioni.applica(una, integ)
    assert una == due


@pytest.mark.parametrize("contenuto", ["", "non e' json", "[1, 2]", '{"nuove": "no", "integra": 5}'])
def test_un_file_rotto_non_rompe_il_catalogo(tmp_path, contenuto):
    f = tmp_path / "i.json"
    f.write_text(contenuto, encoding="utf-8")
    out, _ = integrazioni.applica(CATALOGO, integrazioni.carica(str(f)))
    assert len(out) == len(CATALOGO)


def test_il_file_che_manca_non_e_un_errore():
    assert integrazioni.carica("/non/esiste.json") == {}


def test_l_endpoint_serve_il_catalogo_con_le_acque_nuove(tmp_path, monkeypatch):
    f = tmp_path / "i.json"
    f.write_text(json.dumps({"nuove": [NUOVA]}), encoding="utf-8")
    monkeypatch.setattr(chat, "INTEGRAZIONI", str(f))
    r = TestClient(main.app).get("/catalogo")
    assert r.status_code == 200 and "max-age" in r.headers["cache-control"]
    nomi = [x["NOME_ETICHETTA"] for x in r.json()]
    assert len(nomi) == len(CATALOGO) + 1 and "FONTE DEL TEST" in nomi
    assert set(r.json()[0]) == set(CATALOGO[0])                    # stesso formato del database


def test_senza_il_file_l_endpoint_serve_il_database_com_e(monkeypatch):
    monkeypatch.setattr(chat, "INTEGRAZIONI", "/non/esiste.json")
    assert TestClient(main.app).get("/catalogo").json() == CATALOGO


def test_l_assistente_vede_le_acque_nuove_e_i_valori_corretti(tmp_path, monkeypatch):
    s = _con_nitrati()
    f = tmp_path / "i.json"
    f.write_text(json.dumps({"nuove": [NUOVA], "correggi": [
        {"id": str(s["ID"]), "campo": "NITRATI", "se_ancora": s["NITRATI"], "valore": 1.5}]}), encoding="utf-8")
    monkeypatch.setattr(chat, "INTEGRAZIONI", str(f))
    TestClient(main.app).get("/catalogo")
    schede = {x["id"]: x for x in chat._cache["schede"]}
    assert "90001" in schede and schede["90001"]["nome"] == "FONTE DEL TEST"
    assert schede[str(s["ID"])]["nitrati"] == 1.5


def test_le_correzioni_tolgono_le_incoerenze(tmp_path, monkeypatch):
    """Il motivo per cui si correggono i dati: una scheda sbagliata sparisce
    dalle classifiche, una giusta no."""
    s = next(x for x in CATALOGO if x["SODIO"] not in (None, ""))
    guasto = [dict(x, SODIO="0.01") if x["ID"] == s["ID"] else x for x in CATALOGO]
    sodio, _ = integrazioni.applica(guasto, {"correggi": [
        {"id": str(s["ID"]), "campo": "SODIO", "se_ancora": 0.01, "valore": 14.8}]})
    assert chat._scheda({k.lower(): v for k, v in {x["ID"]: x for x in guasto}[s["ID"]].items()})["incoerenze"]
    assert not chat._scheda({x["ID"]: x for x in sodio}[s["ID"]])["incoerenze"]


def test_una_correzione_puo_svuotare_un_valore_segnaposto():
    s = _con_nitrati()
    regola = {"id": str(s["ID"]), "campo": "NITRATI", "se_ancora": s["NITRATI"], "valore": None}
    out, n = integrazioni.applica(CATALOGO, [] if False else {"correggi": [regola]})
    assert {str(x["ID"]): x for x in out}[str(s["ID"])]["NITRATI"] is None and n["corretti"] == 1
