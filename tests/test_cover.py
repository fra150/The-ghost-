"""Test offline v0.05 cover pre-CoT (nessuna rete, nessun modello esterno).

Misura associata: tasso di copertura degli identificatori strutturati +
residual scan sul coperto + restore integro + mapping inchiodato al bolt.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fantasma.bolt import UseAfterDestroyError  # noqa: E402
from fantasma.pii_cover import (  # noqa: E402
    CoverMapping,
    cf_ok,
    cover_open_classes_with_local_model,
    cover_text,
    find_cover_spans,
    iban_ok,
    luhn_ok,
    piva_ok,
)

CF_OK = "RSSMRA85M01H501Q"
PIVA_OK = "12345678903"
IBAN_OK = "IT60X0542811101000000123456"
CARD_OK = "4111 1111 1111 1111"
MAIL_OK = "m.rossi@studio.it"
PHONE_OK = "+39 333 1234567"


def test_checksum_accettano_validi_e_rifiutano_falsi():
    assert cf_ok(CF_OK) and not cf_ok("RSSMRA85M01H501A")
    assert piva_ok(PIVA_OK) and not piva_ok("12345678901")
    assert iban_ok(IBAN_OK) and not iban_ok("IT60X0542811101000000123457")
    assert luhn_ok("4111111111111111") and not luhn_ok("4111111111111112")


def test_cover_tutti_i_tag_strutturati():
    t = (f"CF {CF_OK}, P.IVA {PIVA_OK}, IBAN {IBAN_OK}, carta {CARD_OK}, "
         f"mail {MAIL_OK}, tel {PHONE_OK}.")
    r = cover_text(t)
    assert r.report["n_values"] == 6
    assert r.report["by_tag"] == {"CF": 1, "PIVA": 1, "IBAN": 1,
                                  "CARD": 1, "EMAIL": 1, "PHONE": 1}
    for v in (CF_OK, PIVA_OK, IBAN_OK, CARD_OK, MAIL_OK, PHONE_OK):
        assert v not in r.covered
    assert "####" not in r.covered


def test_placeholder_disgiunti_da_codice_e_formato_risposta():
    r = cover_text(f"CF {CF_OK} e P.IVA {PIVA_OK}")
    phs = re.findall(r"\[PII_[A-Z]+_\d+\]", r.covered)
    assert len(phs) == 2
    # mai una lunga sequenza di cifre nude, mai formato risposta
    assert not re.search(r"\d{4,}", re.sub(r"\[PII_[A-Z]+_\d+\]", "", r.covered).replace(CF_OK, ""))
    assert "####" not in r.covered


def test_stabile_per_valore_stesso_placeholder():
    t = f"CF {CF_OK} poi ancora CF {CF_OK}"
    r = cover_text(t)
    assert r.report["n_values"] == 1
    assert r.covered.count("[PII_CF_1]") == 2


def test_quantita_nude_restano_intatte():
    # La cover non deve rompere i problemi di matematica.
    t = "Se ho 2880000 euro e la risposta e 54, quanto fa?"
    r = cover_text(t)
    assert r.covered == t
    assert r.report["n_values"] == 0


def test_checksum_invalido_resta_in_chiaro_dichiarato():
    t = "PIVA 12345678901 e CF RSSMRA85M01H501A"
    r = cover_text(t)
    assert r.covered == t  # limite noto: senza checksum valido non si copre


def test_iban_vince_su_sottosequenze_carta():
    spans = find_cover_spans(f"IBAN {IBAN_OK}")
    assert len(spans) == 1 and spans[0][2] == "IBAN"


def test_restore_roundtrip_e_residual_su_coperto():
    t = f"CF {CF_OK}, tel {PHONE_OK}, totale 2880000."
    r = cover_text(t)
    assert r.mapping.values_present_in(r.covered) == []
    assert r.mapping.restore(r.covered) == t


def test_residual_rileva_mancata_copertura_in_output():
    r = cover_text(f"CF {CF_OK}")
    # simula un output che ripete il valore vero nonostante la cover
    assert len(r.mapping.values_present_in(f"ecco il codice {CF_OK}")) == 1


def test_mapping_wipe_e_riuso_rilevato():
    mp = CoverMapping()
    mp.placeholder_for("CF", CF_OK)
    assert len(mp) == 1
    assert mp.wipe() is True
    assert mp.wipe() is False and len(mp) == 0
    for fn in (lambda: mp.restore("x"), lambda: mp.values_present_in("x"),
               lambda: mp.placeholder_for("CF", CF_OK)):
        try:
            fn()
            raise AssertionError("riuso dopo wipe doveva alzare")
        except UseAfterDestroyError:
            pass


def test_guard_compatibile_con_placeholder():
    from fantasma.reform_guard import ReformulationGuard

    g = ReformulationGuard()
    r = cover_text(f"CF {CF_OK}, IBAN {IBAN_OK}, quanto fa 2880000?")
    interp = "Direttiva: scomponi in passi verificabili usando [PII_CF_1]."
    rep = g.validate_with_report(interp, r.covered)
    assert rep["ok"], rep


def test_open_class_con_modello_locale_iniettabile():
    def finto_llm(prompt: str) -> str:
        assert "FANTASMA" not in prompt  # prompt dedicato, non quello del ghost
        return "PERSONA | Mario Rossi\nLUOGO | Via Garibaldi 24"

    t = "Mario Rossi abita in Via Garibaldi 24 a Milano."
    r = cover_open_classes_with_local_model(t, finto_llm)
    assert "Mario Rossi" not in r.covered and "Via Garibaldi 24" not in r.covered
    assert "Milano" in r.covered  # non elencato dal modello: resta, dichiarato
    assert r.mapping.restore(r.covered) == t
    assert r.report["experimental"] is True


def test_open_class_righe_inventate_ignorate():
    def bugiardo(prompt: str) -> str:
        return "PERSONA | Napoleone Bonaparte\nNESSUNO"

    t = "Mario Rossi paga."
    r = cover_open_classes_with_local_model(t, bugiardo)
    assert r.covered == t  # span non nel testo: mai coprire


def test_pipeline_cover_end_to_end():
    from fantasma.pipeline_v02 import FantasmaPipelineV02

    viste = []

    def llm_spia(prompt: str) -> str:
        viste.append(prompt)
        if "FANTASMA-INTERPRETA" in prompt:
            return "Direttiva: scomponi in passi verificabili."
        return "Output finale con [PII_CF_1] citato."

    pipe = FantasmaPipelineV02(llm_fn=llm_spia, cover_pii=True)
    q = (f"Spiega perche questa pratica con CF {CF_OK} e complessa, confronta "
         f"le alternative e valuta i rischi? Tuttavia ci sono vincoli.")
    res = pipe.process(q)
    # il modello non ha mai visto il valore vero
    assert all(CF_OK not in p for p in viste)
    # l'utente riceve il valore ripristinato
    assert CF_OK in res.output
    assert res.meta["cover"] is True
    assert res.meta["cover_residual_n"] == 0
    assert res.meta["bolt_cover"]["entry_hash"]
    assert res.meta["bolts_chain_ok"] is True
    assert res.memory_empty_after and res.cache_empty_after and res.audit_ok
    kinds = [e.kind for e in pipe.audit.events]
    assert "cover_applied" in kinds and "cover_restored" in kinds
    assert "cover_bolted" in kinds
    # mapping distrutto: secondo restore impossibile (catenaccio chiuso)
    assert pipe.bolts.verify_chain() is True


def test_pipeline_senza_cover_invariata():
    from fantasma.pipeline_v02 import FantasmaPipelineV02

    def llm_spia(prompt: str) -> str:
        if "FANTASMA-INTERPRETA" in prompt:
            return "Direttiva: scomponi in passi verificabili."
        return "Output finale spia."

    pipe = FantasmaPipelineV02(llm_fn=llm_spia)  # default: cover off
    q = ("Spiega perche questa decisione strategica e complessa, confronta "
         "le alternative e valuta i rischi? Tuttavia ci sono vincoli.")
    res = pipe.process(q)
    assert res.ghost_activated and "cover" not in res.meta
    assert CF_OK not in q  # sanity: qui non c'erano PII in input
