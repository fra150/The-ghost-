"""Test offline v0.04 Catenaccio software (nessuna rete).

Misura associata (richiesta dal metodo): tasso di rilevazione dei riusi
dopo la distruzione su tutti i percorsi d'uso.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fantasma.bolt import (  # noqa: E402
    BoltRegistry,
    UseAfterDestroyError,
)
from fantasma.crypto import CryptoShredder  # noqa: E402
from fantasma.secret import OneTimeKey, SecretBytes  # noqa: E402


def test_errore_tipizzato_e_sottotipo_valueerror():
    assert issubclass(UseAfterDestroyError, ValueError)


def test_wipe_idempotente_ma_rilevabile():
    s = SecretBytes.from_canonical_19(bytearray(b"0123456789012345678"))
    assert s.wipe() is True
    assert s.is_zeroed()
    assert s.wipe() is False  # secondo wipe: nessun effetto, ma rilevabile


def test_riuso_secret_rilevato_su_tutti_i_percorsi():
    s = SecretBytes.from_canonical_19(bytearray(b"0123456789012345678"))
    s.wipe()
    hits = 0
    for fn in (s.expose_copy, s.decode_at_boundary, s.commitment):
        try:
            fn()
        except UseAfterDestroyError:
            hits += 1
        except ValueError:
            raise AssertionError("deve essere UseAfterDestroyError, non ValueError generico")
    assert hits == 3  # 3/3 percorsi di riuso rilevati


def test_riuso_chiave_e_shredder_rilevato():
    k = OneTimeKey(32)
    k.destroy()
    hits = 0
    for fn in (k.expose, k.expose_mutable, k.region):
        try:
            fn()
        except UseAfterDestroyError:
            hits += 1
    assert hits == 3
    sh = CryptoShredder()
    blob = sh.seal(b"0123456789012345678")
    sh.destroy()
    try:
        sh.open(blob)
        raise AssertionError("open dopo destroy doveva alzare")
    except UseAfterDestroyError:
        hits += 1
    try:
        sh.seal(b"0123456789012345678")
        raise AssertionError("seal dopo destroy doveva alzare")
    except UseAfterDestroyError:
        hits += 1
    assert hits == 5  # 5/5 percorsi rilevati


def test_ricevuta_senza_materiale_del_codice():
    reg = BoltRegistry()
    code = b"0984567345679123456"
    assert len(code) == 19
    uid_hash = "uid-prova-123"
    receipt, first = reg.bolt(uid_hash)
    assert first is True
    d = receipt.to_dict()
    # nessun campo contiene il codice ne' un suo derivato cercabile
    for v in d.values():
        assert code not in str(v).encode("ascii")
        assert code.decode("ascii") not in str(v)
    assert d["uid_hash"] == uid_hash
    assert len(d["nonce_hex"]) == 32 and len(d["entry_hash"]) == 64


def test_catena_integra_e_manomissione_rilevata():
    reg = BoltRegistry()
    for u in ("a", "b", "c"):
        reg.bolt(u)
    assert reg.verify_chain() is True
    assert len(reg) == 3
    # manomissione: sostituisci una voce con prev_hash errato
    r = reg._entries[1]
    reg._entries[1] = type(r)(uid_hash=r.uid_hash, nonce_hex=r.nonce_hex,
                              ts=r.ts, prev_hash="MANOMESSO",
                              entry_hash=r.entry_hash, n=r.n)
    assert reg.verify_chain() is False


def test_bolt_idempotente_stessa_ricevuta():
    reg = BoltRegistry()
    r1, f1 = reg.bolt("uid-x")
    r2, f2 = reg.bolt("uid-x")
    assert (f1, f2) == (True, False)
    assert r1.entry_hash == r2.entry_hash and len(reg) == 1
    assert reg.attempts("uid-x") == 2


def test_pipeline_emette_ricevuta_e_catena():
    from fantasma.pipeline_v02 import FantasmaPipelineV02

    def llm_spia(prompt: str) -> str:
        if "FANTASMA-INTERPRETA" in prompt:
            return "Direttiva: scomponi in passi verificabili."
        return "Output finale spia."

    pipe = FantasmaPipelineV02(llm_fn=llm_spia)
    q = ("Spiega perche' questa decisione strategica e' complessa, confronta "
         "le alternative e valuta i rischi? Tuttavia ci sono vincoli.")
    r1 = pipe.process(q)
    r2 = pipe.process(q + " Variante due.")
    assert r1.meta["bolt"]["uid_hash"] != r2.meta["bolt"]["uid_hash"]
    assert r2.meta["bolt"]["prev_hash"] == r1.meta["bolt"]["entry_hash"]
    assert r2.meta["bolts_chain_ok"] is True
    assert len(pipe.bolts) == 2
    kinds = [e.kind for e in pipe.audit.events]
    assert "bolted" in kinds and "ghost_erased" in kinds
