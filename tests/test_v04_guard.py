"""Test offline v0.04 P0+P1 (nessuna rete, nessun dataset)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fantasma.reform_guard import (  # noqa: E402
    LeakageDetectedError,
    ReformulationGuard,
    build_call1_prompt,
    canonical_numbers_in,
)
from fantasma.secret import (  # noqa: E402
    SecretBytes,
    digest_to_canonical_19,
    random_canonical_19,
    validate_canonical_19,
)


def test_guard_blocca_formato_risposta():
    g = ReformulationGuard()
    try:
        g.validate("Direttiva ok. #### 42", "Quanto fa 1+1?")
        raise AssertionError("doveva bloccare ####")
    except LeakageDetectedError:
        pass


def test_guard_allowlist_numeri_domanda():
    g = ReformulationGuard()
    q = "Marco ha 160000 euro e 3 mele."
    # ripete solo numeri vecchi -> passa anche se denso
    out = g.validate("Riformula: Marco con 160000 euro e 3 mele in passi.", q)
    assert "160000" in out


def test_guard_normalizza_separators():
    assert canonical_numbers_in("160.000 euro") == canonical_numbers_in("160000 euro")
    assert "160000" in canonical_numbers_in("160 mila euro")


def test_guard_blocca_numero_nuovo_lungo():
    g = ReformulationGuard()
    try:
        g.validate("Riformula e calcola 2880000.", "Quanto fa 2+2?")
        raise AssertionError("doveva bloccare numero nuovo lungo")
    except LeakageDetectedError:
        pass


def test_guard_report_struttura():
    g = ReformulationGuard()
    rep = g.validate_with_report("#### 1", "ciao")
    assert rep["ok"] is False and rep["clean"] is None
    assert "new_numbers" in rep and "digit_ratio" in rep


def test_call1_prompt_rigido():
    p = build_call1_prompt("123", "domanda?")
    assert "####" in p and "FANTASMA-INTERPRETA" in p


def test_canonical_validate_ok_ko():
    validate_canonical_19(bytearray(b"0123456789012345678"))
    for bad in (b"123", b"012345678901234567a", b"12345678901234567890"):
        try:
            validate_canonical_19(bytearray(bad))
            raise AssertionError(f"doveva rifiutare {bad!r}")
        except ValueError:
            pass


def test_digest_deterministico_e_uniforme():
    a = digest_to_canonical_19(b"seed")
    b = digest_to_canonical_19(b"seed")
    assert bytes(a) == bytes(b) and len(a) == 19
    assert all(0x30 <= x <= 0x39 for x in a)


def test_random_canonical_19_forma():
    for _ in range(5):
        r = random_canonical_19()
        assert isinstance(r, bytearray) and len(r) == 19
        assert all(0x30 <= x <= 0x39 for x in r)


def test_secretblocca_cast_numerici():
    s = SecretBytes.from_canonical_19(bytearray(b"0123456789012345678"))
    for op in (int, float):
        try:
            op(s)
            raise AssertionError("doveva bloccare cast numerico")
        except TypeError:
            pass
    try:
        s.__index__()
        raise AssertionError("doveva bloccare __index__")
    except TypeError:
        pass
    s.wipe()
    assert s.is_zeroed()


def test_secure_wipe_azzera():
    from fantasma.hygiene import secure_wipe_buffer
    buf = bytearray(b"abcdefgh")
    secure_wipe_buffer(buf)
    assert bytes(buf) == b"\x00" * 8
    try:
        secure_wipe_buffer("no")
        raise AssertionError("doveva rifiutare str")
    except TypeError:
        pass


def test_scrub_traceback_non_alza():
    from fantasma.ghost_window import scrub_traceback
    try:
        raise RuntimeError("prova")
    except RuntimeError as exc:
        n = scrub_traceback(exc)
        assert isinstance(n, int) and n >= 0


def test_arms_con_mock():
    from fantasma.arms import run_arm_random_v04, run_arm_reformonly_v04
    import secrets as _s
    salt = _s.token_bytes(32)

    def llm_clean(prompt: str) -> str:
        if "FANTASMA-INTERPRETA" in prompt:
            return "Direttiva: scomponi in passi verificabili."
        return "#### 4"

    r = run_arm_reformonly_v04(llm_clean, "Quanto fa 2+2?", salt)
    assert r["fallback"] is False and r["output"] == "#### 4"

    calls = {"n": 0}

    def llm_leak(prompt: str) -> str:
        if "FANTASMA-INTERPRETA" in prompt:
            calls["n"] += 1
            return "#### 9999999"
        return "#### 4"

    r2 = run_arm_random_v04(llm_leak, "Quanto fa 2+2?", salt)
    assert r2["fallback"] is True and calls["n"] == 2  # tentativo + 1 retry


def test_ollama_default_deterministico():
    from fantasma.llm_ollama import make_ollama_llm

    class _Fake:
        def generate(self, **kw):
            return {"response": "#### 1", "eval_count": 1,
                    "prompt_eval_count": 1, "total_duration": 1000}

    llm = make_ollama_llm(client=_Fake())
    assert llm("x") == "#### 1"
    assert llm.params["temperature"] == 0.0
    assert llm.params["seed"] == 20261010


def test_deepseek_params_registrati():
    from fantasma.llm_deepseek import get_config
    cfg = get_config()
    assert cfg["temperature"] == 0.0 and cfg["top_p"] == 1.0
