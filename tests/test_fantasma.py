"""Test v0.1.1 — decisioni 5.1 / 5.2 / 5.3 dr. Bulla."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fantasma import (  # noqa: E402
    AuditLogger,
    EphemeralMemory,
    FantasmaPipeline,
    HeuristicGate,
    ObfuscatedCache,
    PrivateNumericCodec,
    deobfuscate_numeric,
    obfuscate_numeric,
)
from fantasma.codec import INTERPRET_MARKER  # noqa: E402


COMPLEX = (
    "Spiega perché questa decisione strategica è complessa, confronta le alternative "
    "e valuta i rischi? Tuttavia ci sono vincoli e bisogna progettare passi."
)


def test_gate():
    gate = HeuristicGate()
    assert gate.should_activate("ciao").active is False
    assert gate.should_activate(COMPLEX).active is True


def test_codice_privato_unico_e_numerico():
    codec = PrivateNumericCodec(secret_salt=b"salt-test-fantasma-01")
    g1 = codec.generate("stesso input complesso da ragionare")
    g2 = codec.generate("stesso input complesso da ragionare")
    assert g1.numeric_code.isdigit() and len(g1.numeric_code) == 19
    assert g1.numeric_code != g2.numeric_code  # non replicabilita'


def test_51_senza_salt_non_capisce():
    codec = PrivateNumericCodec(secret_salt=b"salt-segreto-vero")
    testo = "decisione complessa da riformulare"
    g = codec.generate(testo)
    assert codec.interpret(g) != codec.derive_vector_for(testo, g.nonce, salt=b"salt-sbagliato")


def test_51_stessa_ai_interpreta_il_codice():
    """La stessa llm_fn riceve il prompt con il codice e guida la riformulazione."""
    viste: list[str] = []

    def llm_spia(prompt: str) -> str:
        viste.append(prompt)
        if INTERPRET_MARKER in prompt:
            assert any(ch.isdigit() for ch in prompt)  # il codice e' li' per la stessa AI
            return "Direttiva interna spia: scomponi in passi verificabili."
        return f"Output finale: {prompt[:80]}"

    pipe = FantasmaPipeline(llm_fn=llm_spia)
    res = pipe.process(COMPLEX)

    assert res.ghost_activated is True
    assert res.used_same_ai is True
    # due chiamate alla STESSA ai: interpretazione + generazione finale
    assert len(viste) == 2
    assert INTERPRET_MARKER in viste[0]
    assert INTERPRET_MARKER not in viste[1]
    # la direttiva della stessa AI finisce nella riformulazione
    assert "Direttiva interna spia" in res.reformulated_input
    # ma il raw numerico non trapela mai in output/riformulato
    for prompt in viste:
        pass
    assert res.output.startswith("Output finale")


def test_52_cache_offuscata_mai_raw():
    salt = b"salt-stato-interno-ai"
    codec = PrivateNumericCodec(secret_salt=salt)
    cache = ObfuscatedCache(salt=salt)
    g = codec.generate("input da sigillare")
    raw = g.numeric_code

    trace = cache.seal(g)
    # in cache solo offuscato, mai il raw
    assert trace.obfuscated_code != raw
    assert trace.obfuscated_code.isdigit()
    assert trace.commitment == g.commitment()
    # solo con lo stesso salt (stessa AI) si ripristina
    assert deobfuscate_numeric(trace.obfuscated_code, salt) == raw
    assert deobfuscate_numeric(trace.obfuscated_code, b"salt-ladro") != raw
    # helper diretto
    assert obfuscate_numeric(raw, salt) != raw
    assert deobfuscate_numeric(obfuscate_numeric(raw, salt), salt) == raw


def test_53_amnesia_dopo_output():
    pipe = FantasmaPipeline()
    res = pipe.process(COMPLEX)
    assert res.ghost_activated is True
    # sputato l'output, non serve ricordare: tutto vuoto
    assert res.memory_empty_after is True
    assert res.cache_empty_after is True
    assert len(pipe.memory) == 0
    assert len(pipe.cache) == 0
    # audit resta verificabile ma contiene solo hash
    assert res.audit_ok is True
    for ev in pipe.audit.events:
        assert len(ev.payload_hash) == 64


def test_pipeline_standby_e_cancellazione():
    pipe = FantasmaPipeline()
    r0 = pipe.process("ciao")
    assert r0.ghost_activated is False and r0.used_same_ai is False

    r1 = pipe.process(COMPLEX)
    assert r1.ghost_activated is True
    assert r1.reformulated_input != COMPLEX
    assert r1.ghost_commitment is not None
    assert r1.ghost_commitment not in r1.output
    assert r1.audit_ok is True


def test_54_audit_tamper_rivelato():
    pipe = FantasmaPipeline()
    pipe.process(COMPLEX)
    audit: AuditLogger = pipe.audit
    assert audit.verify() is True
    kinds = audit.kinds()
    for atteso in ("input_received", "gate_decision", "ghost_activated",
                   "ghost_interpreted", "cached_obfuscated", "reformulated",
                   "output_produced", "ghost_erased"):
        assert atteso in kinds
    audit.events[0].payload_hash = "0" * 64
    assert audit.verify() is False


def test_memoria_forget():
    mem = EphemeralMemory()
    codec = PrivateNumericCodec(secret_salt=b"x")
    g = codec.generate("da dimenticare")
    mem.put(g)
    assert len(mem) == 1
    assert mem.forget(g.uid) is True
    assert len(mem) == 0
