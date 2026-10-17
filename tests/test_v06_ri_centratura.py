"""Test v0.06 — ri-centratura: nascita uniforme, blinding, ciclo nominato.

Prerequisiti del paper corretto v0.05 (r.115/r.117): la correzione del bias
di nascita (~49,5 -> 63,1 bit effettivi) e il blinding 128 bit distrutto a
expire(). Piu' il ciclo nominato (CICLO_V006) e l'ordine delle morti
(wipe del mapping prima del bolt che lo registra).
Nessuna rete, nessun modello esterno: mock locali.
"""

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import fantasma.pipeline_v02 as pv  # noqa: E402
from fantasma import CICLO_V006  # noqa: E402
from fantasma.bolt import BoltRegistry  # noqa: E402
from fantasma.codec import PrivateNumericCodec  # noqa: E402
from fantasma.crypto import CryptoShredder  # noqa: E402
from fantasma.pii_cover import CoverMapping  # noqa: E402
from fantasma.pipeline_v02 import FantasmaPipelineV02  # noqa: E402
from fantasma.secret import digest_to_canonical_19  # noqa: E402

CF_OK = "RSSMRA85M01H501Q"

Q_COMPLEX = (
    "Spiega perché questa decisione strategica è complessa, confronta le alternative "
    "e valuta i rischi? Tuttavia ci sono vincoli e bisogna progettare passi."
)

Q_COVER = (
    f"Spiega perche questa pratica con CF {CF_OK} e complessa, confronta "
    f"le alternative e valuta i rischi? Tuttavia ci sono vincoli."
)


def test_nascita_uniforme_mai_piu_f_string_troncato():
    """19 cifre uniformi via rejection sampling; il vecchio schema era biasato.

    Deterministico (digest fissi), niente soglie fragili:
    - vecchio f"{b:03d}" troncato: il primo digit sta SEMPRE in {0,1,2}
      (ogni byte 0..255 ha rappresentazione a 3 cifre che inizia con 0-2);
    - nuovo digest_to_canonical_19: primo digit uniforme su 0-9. Atteso
      ~19/64 in {0,1,2}; soglia larghissima (<40) e >=6 valori distinti.
    """
    digests = [hashlib.sha256(f"nascita-{i}".encode()).digest() for i in range(64)]

    nuovi = [bytes(digest_to_canonical_19(d)).decode("ascii") for d in digests]
    for s in nuovi:
        assert len(s) == 19 and s.isdigit()
    primi = [s[0] for s in nuovi]
    assert len(set(primi)) >= 6, f"primi digit troppo concentrati: {sorted(set(primi))}"
    bassi = sum(1 for p in primi if p in "012")
    assert bassi < 40, f"bias residuo: {bassi}/64 con primo digit in 0-2"

    # contrasto esatto col vecchio schema: bias strutturale, non probabilistico
    vecchi = ["".join(f"{b:03d}" for b in d)[:19] for d in digests]
    assert all(s[0] in "012" for s in vecchi)

    # il codec pubblico passa dallo stesso percorso uniforme
    codec = PrivateNumericCodec(secret_salt=b"S" * 32)
    fisso = hashlib.sha256(b"codec-v06").digest()
    atteso = bytes(digest_to_canonical_19(fisso)).decode("ascii")
    assert codec._to_numeric(fisso) == atteso  # noqa: SLF001
    pensiero = codec.generate("prova")
    assert len(pensiero.numeric_code) == 19 and pensiero.numeric_code.isdigit()


def test_impegno_legato_a_salt_nonce_input(monkeypatch):
    """Stessa terna (salt, nonce, input) -> stesso fantasma; nonce diverso -> diverso.

    La nascita resta deterministica a parita' di digest (legame col giro),
    ma il nonce fresco rende ogni giro un fantasma diverso: il commitment
    e' funzione di (salt, nonce, input), niente altro.
    """

    class _Uuid:
        def __init__(self, h: str) -> None:
            self.hex = h

    seq = iter([
        _Uuid("a" * 32), _Uuid("1" * 32),  # run 1: nonce, uid
        _Uuid("a" * 32), _Uuid("2" * 32),  # run 2: stesso nonce, uid diverso
        _Uuid("b" * 32), _Uuid("3" * 32),  # run 3: nonce diverso
    ])
    monkeypatch.setattr(pv.uuid, "uuid4", lambda: next(seq))

    def llm_mock(prompt: str) -> str:
        if "FANTASMA-INTERPRETA" in prompt:
            return "Direttiva interna: scomponi in passi verificabili."
        return f"Output finale: {prompt[:60]}"

    salt = b"V" * 32
    p1 = FantasmaPipelineV02(secret_salt=salt, llm_fn=llm_mock)
    r1 = p1.process(Q_COMPLEX)
    p2 = FantasmaPipelineV02(secret_salt=salt, llm_fn=llm_mock)
    r2 = p2.process(Q_COMPLEX)
    p3 = FantasmaPipelineV02(secret_salt=salt, llm_fn=llm_mock)
    r3 = p3.process(Q_COMPLEX)

    assert r1.ghost_activated and r2.ghost_activated and r3.ghost_activated
    assert r1.ghost_commitment == r2.ghost_commitment  # stessa terna -> stesso fantasma
    assert r3.ghost_commitment != r1.ghost_commitment  # nonce diverso -> fantasma diverso


def test_ciclo_nominato_meta_fase_e_ordine():
    """CICLO_V006 esportato + meta 'fase' sugli eventi, nell'ordine del ciclo."""
    assert CICLO_V006 == ("input", "CoT", "emerge", "agisce", "scompare",
                          "doppio_catenaccio", "output")

    def llm_spia(prompt: str) -> str:
        if "FANTASMA-INTERPRETA" in prompt:
            return "Direttiva: scomponi in passi verificabili."
        return "Output finale con [PII_CF_1] citato."

    pipe = FantasmaPipelineV02(llm_fn=llm_spia, cover_pii=True)
    res = pipe.process(Q_COVER)
    assert res.ghost_activated is True and res.meta["cover"] is True
    # il wipe esplicito del mapping e' avvenuto (prima del bolt: test sotto)
    assert res.meta["mapping_wiped"] is True

    tagged = [e for e in pipe.audit.events if "fase" in e.meta]
    fases = [e.meta["fase"] for e in tagged]
    # ogni fase usata appartiene al ciclo e "CoT" resta muta (nessun evento)
    assert set(fases) <= set(CICLO_V006)
    assert "CoT" not in fases
    # ordine dei keystone (l'evento "output" e' la produzione del testo; la
    # consegna avviene dopo l'amnesia, quindi il ciclo lo legge in coda)
    pos = -1
    for nome in ("input", "emerge", "agisce", "scompare", "doppio_catenaccio"):
        pos = fases.index(nome, pos + 1)
    assert "output" in fases
    # per-evento: chiave -> fase
    per_kind = {e.kind: e.meta["fase"] for e in tagged}
    assert per_kind["input_received"] == "input"
    assert per_kind["ghost_activated"] == "emerge"
    assert per_kind["ghost_interpreted"] == "agisce"
    assert per_kind["reformulated"] == "agisce"
    assert per_kind["output_produced"] == "output"
    assert per_kind["ghost_erased"] == "scompare"
    assert per_kind["bolted"] == "doppio_catenaccio"
    assert per_kind["cover_bolted"] == "doppio_catenaccio"


def test_ricevute_emesse_dalle_morti_e_concatenate(monkeypatch):
    """Ordine delle morti: wipe/destroy PRIMA del bolt; ricevute concatenate.

    La ricevuta non sostituisce la morte: la registra. E la catena dei due
    bolt (principale + cover) si chiude: prev del secondo = entry del primo.
    """
    eventi: list[str] = []

    orig_wipe = CoverMapping.wipe

    def wipe_spia(self):
        r = orig_wipe(self)
        if r:
            eventi.append("cover_wipe")
        return r

    monkeypatch.setattr(CoverMapping, "wipe", wipe_spia)

    orig_bolt = BoltRegistry.bolt

    def bolt_spia(self, uid):
        eventi.append("bolt_cover" if str(uid).startswith("cover:") else "bolt")
        return orig_bolt(self, uid)

    monkeypatch.setattr(BoltRegistry, "bolt", bolt_spia)

    orig_destroy = CryptoShredder.destroy

    def destroy_spia(self):
        eventi.append("destroy_chiave")
        return orig_destroy(self)

    monkeypatch.setattr(CryptoShredder, "destroy", destroy_spia)

    def llm_spia(prompt: str) -> str:
        if "FANTASMA-INTERPRETA" in prompt:
            return "Direttiva: scomponi in passi verificabili."
        return "Output finale con [PII_CF_1] citato."

    pipe = FantasmaPipelineV02(llm_fn=llm_spia, cover_pii=True)
    res = pipe.process(Q_COVER)

    # la morte della chiave precede la sua ricevuta; idem per il mapping
    assert "destroy_chiave" in eventi and "bolt" in eventi
    assert eventi.index("destroy_chiave") < eventi.index("bolt")
    assert eventi.index("cover_wipe") < eventi.index("bolt_cover")
    # catena: il bolt cover parte dall'entry del bolt principale
    assert res.meta["bolt_cover"]["prev_hash"] == res.meta["bolt"]["entry_hash"]
    # "first" = prima volta per QUEL uid, non prima voce della catena
    assert res.meta["bolt_first"] is True
    assert res.meta["bolt_cover_first"] is True
    assert pipe.bolts.verify_chain() is True
