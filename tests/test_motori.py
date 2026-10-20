"""Motori di riserva: se Google non risponde, la domanda passa ad altri."""
import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

import chat
import main

CHIAVE_ESTERNA = "sk-chiave-esterna-segretissima"


def esterno(monkeypatch, *, url="https://api.deepseek.com/chat/completions", modello="deepseek-chat",
            chiave=CHIAVE_ESTERNA, altri=()):
    """Imposta i servizi esterni come li leggerebbe il server."""
    elenco = [chat._esterno(chiave, url, modello)] if chiave else []
    elenco += [chat._esterno(*x) for x in altri]
    monkeypatch.setattr(chat, "ESTERNI", elenco)


@pytest.fixture(autouse=True)
def pulito(monkeypatch):
    monkeypatch.setattr(chat, "CACHE_ATTIVA", False)
    chat._risposte.svuota()
    chat._testi.svuota()
    chat._uso.update(giorno="", per_chi={}, totale=0)
    chat._cache.update(schede=[], grezzo=[], letto=0.0, impronta="", integrazioni={})
    chat._interruttore.update(guasti=[], fino=0.0)
    chat._motore_guasto.clear()
    chat._per_motore.clear()
    monkeypatch.setattr(chat, "PAUSE_RIPROVA", (0.0, 0.0))
    yield


def _g(testo):
    return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": testo}]}}],
                                     "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 2}})


def _openai(testo, fine="stop"):
    return httpx.Response(200, json={"choices": [{"message": {"content": testo}, "finish_reason": fine}],
                                     "usage": {"prompt_tokens": 5, "completion_tokens": 4}})


GIU = httpx.Response(503, json={"error": {"status": "UNAVAILABLE"}})


def _rete(monkeypatch, per_url):
    """per_url: lista di (frammento dell'URL, risposta o funzione). Ricorda le richieste."""
    visti = []

    def risponde(req):
        corpo = json.loads(req.content)
        visti.append((str(req.url), dict(req.headers), corpo))
        for frammento, ris in per_url:
            if frammento in str(req.url):
                return ris(req) if callable(ris) else ris
        return httpx.Response(404)
    monkeypatch.setattr(chat, "_ipv4", lambda: httpx.MockTransport(risponde))
    return visti


def chiedi(testo="ciao"):
    return asyncio.run(chat._gemini(testo, sistema="regole"))


def test_senza_riserve_si_comporta_come_prima(monkeypatch):
    visti = _rete(monkeypatch, [("generateContent", GIU)])
    with pytest.raises(chat.GeminiErrore):
        chiedi()
    assert len(visti) == 3                          # tre tentativi, un solo motore


def test_se_il_principale_e_giu_risponde_la_riserva_google(monkeypatch):
    monkeypatch.setattr(chat, "RISERVE_GEMINI", ["modello-riserva"])
    visti = _rete(monkeypatch, [("modello-riserva", _g("dalla riserva")), (chat.MODEL, GIU)])
    assert chiedi() == "dalla riserva"
    assert [chat.MODEL in v[0] for v in visti] == [True, False]       # una sola prova sul principale
    assert chat._per_motore == {"modello-riserva": 1}


def test_il_principale_che_torna_su_riprende_il_suo_posto(monkeypatch):
    monkeypatch.setattr(chat, "RISERVE_GEMINI", ["modello-riserva"])
    orologio = [1000.0]
    monkeypatch.setattr(chat.time, "time", lambda: orologio[0])
    _rete(monkeypatch, [("modello-riserva", _g("riserva")), (chat.MODEL, GIU)])
    chiedi()
    assert chat._motori()[0][0] == "modello-riserva"                  # il giu' va in fondo
    orologio[0] += chat.PAUSA_MOTORE_GUASTO + 1
    assert chat._motori()[0][0] == chat.MODEL                         # passato il tempo, riprova


def test_durante_l_interruzione_le_domande_successive_vanno_dritte_alla_riserva(monkeypatch):
    monkeypatch.setattr(chat, "RISERVE_GEMINI", ["modello-riserva"])
    visti = _rete(monkeypatch, [("modello-riserva", _g("riserva")), (chat.MODEL, GIU)])
    chiedi(); chiedi(); chiedi()
    sul_principale = [v for v in visti if chat.MODEL in v[0]]
    assert len(sul_principale) == 1                                   # solo la prima ha perso tempo


def test_se_google_e_tutto_giu_risponde_il_servizio_esterno(monkeypatch):
    monkeypatch.setattr(chat, "RISERVE_GEMINI", ["modello-riserva"])
    esterno(monkeypatch, url="https://esterno.test/chat/completions", modello="modello-esterno")
    visti = _rete(monkeypatch, [("esterno.test", _openai("dal servizio esterno")), ("generateContent", GIU)])
    assert chiedi() == "dal servizio esterno"
    url, intestazioni, corpo = visti[-1]
    assert intestazioni["authorization"] == f"Bearer {CHIAVE_ESTERNA}"
    assert "x-goog-api-key" not in intestazioni                         # la chiave di Google non esce
    assert corpo["model"] == "modello-esterno" and "esterno.test" in url
    assert [m["role"] for m in corpo["messages"]] == ["system", "user"]
    assert chat._per_motore == {"esterno/modello-esterno": 1}


def test_al_servizio_esterno_si_chiede_json_e_si_descrive_lo_schema(monkeypatch):
    monkeypatch.setattr(chat, "RISERVE_GEMINI", [])
    esterno(monkeypatch)
    visti = _rete(monkeypatch, [("generateContent", GIU), ("deepseek", _openai('{"azione": "saluto"}'))])
    schema = {"type": "OBJECT", "properties": {"azione": {"type": "STRING"}}}
    out = asyncio.run(chat._gemini("ciao", sistema="regole", schema=schema))
    assert json.loads(out) == {"azione": "saluto"}
    corpo = visti[-1][2]
    assert corpo["response_format"] == {"type": "json_object"}
    assert "JSON" in corpo["messages"][0]["content"] and '"azione"' in corpo["messages"][0]["content"]


def test_senza_schema_non_si_chiede_json(monkeypatch):
    monkeypatch.setattr(chat, "RISERVE_GEMINI", [])
    esterno(monkeypatch)
    visti = _rete(monkeypatch, [("generateContent", GIU), ("deepseek", _openai("testo libero"))])
    chiedi()
    assert "response_format" not in visti[-1][2]


def test_senza_chiave_il_servizio_esterno_non_si_usa(monkeypatch):
    monkeypatch.setattr(chat, "RISERVE_GEMINI", [])
    esterno(monkeypatch, chiave="")
    assert [t for _, t in chat._motori()] == ["gemini"]


def test_i_token_del_servizio_esterno_si_contano(monkeypatch):
    monkeypatch.setattr(chat, "RISERVE_GEMINI", [])
    esterno(monkeypatch)
    chat._uso.update(token_in=0, token_out=0)
    _rete(monkeypatch, [("generateContent", GIU), ("deepseek", _openai("ok"))])
    chiedi()
    assert chat._uso["token_in"] == 5 and chat._uso["token_out"] == 4


def test_una_risposta_troncata_del_servizio_esterno_non_vale(monkeypatch):
    monkeypatch.setattr(chat, "RISERVE_GEMINI", [])
    esterno(monkeypatch)
    _rete(monkeypatch, [("generateContent", GIU), ("deepseek", _openai("tagliata a me", fine="length"))])
    with pytest.raises(chat.GeminiErrore, match="troncata"):
        chiedi()


def test_se_tutti_i_motori_sono_giu_l_errore_e_quello_di_prima(monkeypatch):
    monkeypatch.setattr(chat, "RISERVE_GEMINI", ["modello-riserva"])
    esterno(monkeypatch)
    _rete(monkeypatch, [("generateContent", GIU), ("deepseek", httpx.Response(402, json={"error": {"message": "saldo"}}))])
    with pytest.raises(chat.GeminiErrore, match="HTTP 402"):
        chiedi()


def test_un_errore_di_contenuto_non_manda_il_motore_in_coda(monkeypatch):
    """Una risposta vuota riguarda quella domanda, non dice che Google e' giu'."""
    monkeypatch.setattr(chat, "RISERVE_GEMINI", ["modello-riserva"])
    _rete(monkeypatch, [("modello-riserva", _g("ok")), (chat.MODEL, _g("   "))])
    assert chiedi() == "ok"
    assert chat.MODEL not in chat._motore_guasto


def test_il_tempo_massimo_ferma_la_catena(monkeypatch):
    monkeypatch.setattr(chat, "RISERVE_GEMINI", ["modello-riserva"])
    visti = _rete(monkeypatch, [("generateContent", _g("mai"))])
    with pytest.raises(chat.GeminiErrore, match="tempo esaurito"):
        asyncio.run(chat._gemini("x", sistema="r", scadenza=chat.time.time() + 1))
    assert visti == []


def test_la_domanda_dell_utente_arriva_a_una_domanda_vera_con_la_riserva(monkeypatch):
    """Dall'inizio alla fine: Google giu', risponde il servizio esterno e l'utente ha la sua risposta."""
    monkeypatch.setattr(chat, "RISERVE_GEMINI", [])
    esterno(monkeypatch)
    piano = json.dumps({"azione": "scheda", "acque": ["Ferrarelle"], "parametri": ["magnesio"]})
    _rete(monkeypatch, [("generateContent", GIU),
                        ("deepseek", lambda req: _openai(piano if "Struttura" in json.loads(req.content)["messages"][0]["content"]
                                                         else "FERRARELLE: magnesio 25 mg/L."))])
    r = TestClient(main.app).post("/chat", json={"domanda": "Quanto magnesio c'e' nella Ferrarelle?"})
    assert r.status_code == 200 and r.json()["modalita"] == "modello"
    assert "25" in r.json()["risposta"] and r.json()["acque"]


def test_lo_stato_dice_i_motori_ma_non_le_chiavi(monkeypatch, capsys):
    monkeypatch.setattr(chat, "RISERVE_GEMINI", ["modello-riserva"])
    esterno(monkeypatch)
    _rete(monkeypatch, [("generateContent", GIU), ("deepseek", _openai("ok"))])
    chiedi()
    stato = TestClient(main.app).get("/chat/stato").json()
    # Chi non ha risposto scende in fondo: ora il servizio esterno e' il primo.
    assert stato["motori"][0] == "deepseek/deepseek-chat" and stato["risposte_per_motore"] == {"deepseek/deepseek-chat": 1}
    assert chat.MODEL in stato["motori_in_coda"]
    assert CHIAVE_ESTERNA not in json.dumps(stato) and CHIAVE_ESTERNA not in capsys.readouterr().out


def test_piu_servizi_esterni_si_provano_nell_ordine_e_il_primo_che_risponde_vince(monkeypatch):
    monkeypatch.setattr(chat, "RISERVE_GEMINI", [])
    esterno(monkeypatch, url="https://api.groq.com/openai/v1/chat/completions", modello="llama-gratis",
            altri=[(CHIAVE_ESTERNA + "2", "https://api.deepseek.com/chat/completions", "deepseek-chat")])
    visti = _rete(monkeypatch, [("generateContent", GIU), ("groq.com", GIU), ("deepseek.com", _openai("da deepseek"))])
    assert chiedi() == "da deepseek"
    assert [("groq" in v[0], "deepseek" in v[0]) for v in visti if "generateContent" not in v[0]] == [(True, False), (False, True)]
    assert set(chat._motore_guasto) >= {chat.MODEL, "groq/llama-gratis"}


def test_la_chiave_di_un_servizio_non_va_a_un_altro(monkeypatch):
    monkeypatch.setattr(chat, "RISERVE_GEMINI", [])
    esterno(monkeypatch, url="https://api.groq.com/openai/v1/chat/completions", modello="llama-gratis", chiave="chiave-groq",
            altri=[("chiave-deepseek", "https://api.deepseek.com/chat/completions", "deepseek-chat")])
    visti = _rete(monkeypatch, [("generateContent", GIU), ("groq.com", GIU), ("deepseek.com", _openai("ok"))])
    chiedi()
    for url, intestazioni, _ in visti:
        if "groq.com" in url:
            assert intestazioni["authorization"] == "Bearer chiave-groq"
        if "deepseek.com" in url:
            assert intestazioni["authorization"] == "Bearer chiave-deepseek"


def test_i_gratuiti_vanno_prima_del_deepseek_a_pagamento(monkeypatch):
    for k in ("LLM_RISERVA_KEY", "LLM_RISERVA2_KEY", "LLM_RISERVA3_KEY", "LLM_RISERVA4_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("LLM_RISERVA_KEY", "k-deepseek")                    # slot senza numero: DeepSeek
    monkeypatch.setenv("LLM_RISERVA3_KEY", "k-cerebras")
    monkeypatch.setenv("LLM_RISERVA3_URL", "https://api.cerebras.ai/v1/chat/completions")
    monkeypatch.setenv("LLM_RISERVA3_MODELLO", "llama-x")
    monkeypatch.setenv("LLM_RISERVA2_KEY", "k-groq")
    monkeypatch.setenv("LLM_RISERVA2_URL", "https://api.groq.com/openai/v1/chat/completions")
    monkeypatch.setenv("LLM_RISERVA2_MODELLO", "llama-y")
    assert [e["nome"] for e in chat._leggi_esterni()] == ["groq/llama-y", "cerebras/llama-x", "deepseek/deepseek-chat"]


def test_uno_slot_incompleto_si_ignora(monkeypatch):
    for k in ("LLM_RISERVA_KEY", "LLM_RISERVA2_KEY", "LLM_RISERVA3_KEY", "LLM_RISERVA4_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("LLM_RISERVA2_KEY", "k-senza-url")                  # manca URL e modello
    assert chat._leggi_esterni() == []


@pytest.mark.parametrize("url,atteso", [("https://api.groq.com/openai/v1/chat/completions", "groq/m"),
                                        ("https://api.cerebras.ai/v1/chat/completions", "cerebras/m"),
                                        ("https://api.mistral.ai/v1/chat/completions", "mistral/m"),
                                        ("http://localhost:8080/v1/chat/completions", "localhost:8080/m")])
def test_il_nome_del_motore_dice_chi_e(url, atteso):
    assert chat._esterno("k", url, "m")["nome"] == atteso


def test_i_parametri_extra_del_servizio_arrivano_nella_richiesta(monkeypatch):
    monkeypatch.setattr(chat, "RISERVE_GEMINI", [])
    monkeypatch.setattr(chat, "ESTERNI", [chat._esterno("k", "https://api.groq.com/openai/v1/chat/completions",
                                                         "openai/gpt-oss-120b", {"reasoning_effort": "low"})])
    visti = _rete(monkeypatch, [("generateContent", GIU), ("groq.com", _openai("ok"))])
    chiedi()
    assert visti[-1][2]["reasoning_effort"] == "low" and visti[-1][2]["model"] == "openai/gpt-oss-120b"


def test_gli_extra_si_leggono_dall_ambiente_e_un_json_rotto_si_ignora(monkeypatch):
    for k in ("LLM_RISERVA_KEY", "LLM_RISERVA2_KEY", "LLM_RISERVA3_KEY", "LLM_RISERVA4_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("LLM_RISERVA2_KEY", "k")
    monkeypatch.setenv("LLM_RISERVA2_URL", "https://api.groq.com/openai/v1/chat/completions")
    monkeypatch.setenv("LLM_RISERVA2_MODELLO", "m")
    monkeypatch.setenv("LLM_RISERVA2_EXTRA", '{"reasoning_effort": "low"}')
    assert chat._leggi_esterni()[0]["extra"] == {"reasoning_effort": "low"}
    monkeypatch.setenv("LLM_RISERVA2_EXTRA", "{non e json")
    assert chat._leggi_esterni()[0]["extra"] == {}
    monkeypatch.setenv("LLM_RISERVA2_EXTRA", "[1, 2]")
    assert chat._leggi_esterni()[0]["extra"] == {}
