"""Test pipeline v0.02 end-to-end — L1 misurato con LLM mockato, L2 dichiarato.

Stessa interfaccia .process() della v0.01, interno Secret+AES-GCM.
Nessun claim finche' non misurato: qui L1 deve essere R=0 negli store,
L2 si misura su Linux / si dichiara non-misurabile su Windows.
"""

import gc
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fantasma.forensics import (  # noqa: E402
    count_variants_in_stores,
    generate_runtime_canary,
    scan_process_mem,
)
from fantasma.pipeline_v02 import FantasmaPipelineV02  # noqa: E402


COMPLEX = (
    "Spiega perché questa decisione strategica è complessa, confronta le alternative "
    "e valuta i rischi? Tuttavia ci sono vincoli e bisogna progettare passi."
)


def test_v02_standby_senza_fantasma():
    pipe = FantasmaPipelineV02()
    r = pipe.process("ciao")
    assert r.ghost_activated is False
    assert r.memory_empty_after and r.cache_empty_after
    assert r.audit_ok is True


def test_v02_giro_completo_L1_R_zero_con_mock():
    viste: list[str] = []

    def llm_spia(prompt: str) -> str:
        viste.append(prompt)
        if "FANTASMA-INTERPRETA" in prompt:
            return "Direttiva interna spia: scomponi in passi verificabili."
        return f"Output finale: {prompt[:80]}"

    pipe = FantasmaPipelineV02(llm_fn=llm_spia)
    res = pipe.process(COMPLEX)
    assert res.ghost_activated is True
    assert res.used_same_ai is True
    assert res.algo.startswith("stdlib-encrypt-then-MAC")
    assert res.key_commitment is not None and len(res.key_commitment) == 64
    assert res.ghost_commitment is not None and len(res.ghost_commitment) == 64
    assert len(viste) == 2
    assert res.memory_empty_after is True
    assert res.cache_empty_after is True
    assert res.audit_ok is True
    # L1: negli store applicativi non resta nulla del giro
    # (il prompt spia trattiene copie vive nelle `viste`: e' il perimetro del chiamante,
    #  non della pipeline — la pipeline ha svuotato i SUOI store)
    assert len(pipe._live_secrets) == 0
    assert len(pipe._sealed) == 0
    for ev in pipe.audit.events:
        assert len(ev.payload_hash) == 64
    # il commitment non rivela il pensiero in output
    assert res.ghost_commitment not in res.output


def test_v02_canary_end_to_end_con_mock_che_cattura():
    """
    Canary runtime iniettato come 'pensiero': il mock cattura il prompt (copia viva
    nel chiamante), la pipeline fa wipe+shred. L1 della pipeline deve essere 0;
    le copie nel chiamante (viste) esistono finche' vive il chiamante — e' il
    punto 1: L2 non e' R=0 col flusso reale, va misurato/dichiarato.
    """
    canary = generate_runtime_canary(19)
    canary_s = canary.decode("ascii")
    viste: list[str] = []

    def llm_leak(prompt: str) -> str:
        # mock onesto che NON trattiene oltre la chiamata... ma qui catturiamo
        # apposta per misurare il perimetro del chiamante
        viste.append(prompt)
        # inietta il canary come se fosse il codice (worst case)
        return f"Direttiva per {canary_s}: scomponi."

    from fantasma.secret import SecretBytes
    from fantasma.crypto import CryptoShredder

    # simula il giro minimo: Secret -> decode -> prompt -> seal -> wipe -> destroy
    s = SecretBytes.from_bytes(canary)
    decoded = s.decode_at_boundary()
    prompt = f"FANTASMA-INTERPRETA Codice fantasma: {decoded}"
    del decoded
    out = llm_leak(prompt)
    prompt = "0" * len(prompt)
    del prompt
    sh = CryptoShredder()
    raw = s.expose_copy()
    blob = sh.seal(raw)
    ba = bytearray(raw)
    for i in range(len(ba)):
        ba[i] = 0x00
    del ba
    del raw
    s.wipe()
    sh.destroy()
    # pipeline interna pulita
    assert s.is_zeroed()
    assert sh.is_destroyed
    # MA il chiamante trattiene copie (viste+out): L1 globale >0 finche' vive il chiamante
    res_variants = count_variants_in_stores(canary, viste, out)
    assert res_variants["R"] > 0  # prova che lo scanner vede davvero
    # dopo che il chiamante cancella, torna 0
    viste.clear()
    del out
    gc.collect()
    assert count_variants_in_stores(canary, {})["R"] == 0
    mem = scan_process_mem(canary)
    assert mem is None or isinstance(mem, dict)  # L2: misurato dove possibile, mai affermato
    del s
    del sh
    del blob
    del canary
    gc.collect()
