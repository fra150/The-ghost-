"""Test claim integrity v0.02 — punti 2,3,4,5,6 della revisione.

- test_l1_positive_control: positivo+negativo obbligatori (punto 4);
- test_R_sottrae_legittime: R = trovate - legittime (punto 3);
- test_claim_condizionale_a_hygiene: L2 solo se hygiene verde (punto 2);
- test_no_fork_in_ghost_window: fork vietato nella finestra (punto 5);
- test_exception_frame_scrubbed: frame scrub + wipe in finally (punto 6);
- test_mlock_puntuale_report: lock per-pagina, mai mlockall (punto 1).
"""

import gc
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fantasma.forensics import (  # noqa: E402
    assert_scanner_sane,
    count_needle_in_stores,
    count_unexpected,
    evaluate_claim,
    generate_runtime_canary,
)
from fantasma.ghost_window import (  # noqa: E402
    assert_no_fork_in_window,
    ghost_window,
    scrub_frame_locals,
)
from fantasma.hygiene import apply_process_hygiene, lock_secret_region  # noqa: E402
from fantasma.secret import SecretBytes  # noqa: E402


def test_l1_positive_control():
    canary = generate_runtime_canary(19)
    # positivo + negativo: senza positivo, R=0 non significa niente (punto 4)
    assert_scanner_sane(canary)
    # il nostro L1 non usa gc.get_objects (punto cieco): attraversa gli store
    probe = {"x": bytes(canary).decode("ascii")}
    assert count_needle_in_stores(canary, probe) >= 1
    assert count_needle_in_stores(canary, {}) == 0
    del canary
    gc.collect()


def test_R_sottrae_legittime():
    canary = generate_runtime_canary(19)
    # lo scanner possiede il canary: 1 copia legittima dichiarata
    holder = {"a": bytes(canary).decode("ascii")}
    r1 = count_unexpected(canary, (holder,), n_legitimate=1)
    assert r1["found"] >= 1 and r1["R"] == r1["found"] - 1
    # senza altre copie, R inatteso = 0 anche se found = 1 legittima
    holder2 = {"a": bytes(canary).decode("ascii")}
    r2 = count_unexpected(canary, (holder2,), n_legitimate=1)
    assert r2["ok"] is True
    # leak vera: 2 copie distinte, 1 legittima -> R>=1
    # nota: bytes(canary) restituisce lo STESSO oggetto (immutabile), quindi
    # per la seconda copia serve un oggetto distinto (bytearray->bytes)
    leak = {"a": bytes(canary).decode("ascii"), "b": bytes(bytearray(bytes(canary)))}
    r3 = count_unexpected(canary, (leak,), n_legitimate=1)
    assert r3["R"] >= 1 and r3["ok"] is False
    del canary
    gc.collect()


def test_claim_condizionale_a_hygiene():
    hyg = apply_process_hygiene()
    # L1 pulito + hygiene verde + mem pulita (simulata) -> overall solo se tutto ok
    fake_mem_clean = {"raw": 0, "utf16le": 0, "utf16be": 0, "_regions_scanned": 10}
    c = evaluate_claim(store_R=0, hygiene_report=hyg, mem_scan=fake_mem_clean)
    assert c["L1_store_R0"] is True
    assert c["L3_claim"].startswith("mai affermato")
    assert c["boundary"] == "R=0 entro i confini misurabili del processo"
    # hygiene rossa -> L2 NON affermato anche con mem pulita (punto 2)
    bad_hyg = dict(hyg)
    bad_hyg["rlimit_core_ok"] = False
    c2 = evaluate_claim(store_R=0, hygiene_report=bad_hyg, mem_scan=fake_mem_clean)
    assert c2["L2_claim"] == "NON affermato"
    # mem non disponibile (Windows) -> L2 NON affermato, L1 resta
    c3 = evaluate_claim(store_R=0, hygiene_report=hyg, mem_scan=None)
    assert c3["L2_claim"] == "NON affermato"
    assert c3["L1_claim"] == "affermabile"


def test_no_fork_in_ghost_window():
    # punto 5: dentro la finestra fork solleva (o piattaforma senza fork)
    assert_no_fork_in_window()
    import os

    if hasattr(os, "fork"):
        with ghost_window():
            try:
                os.fork()
            except RuntimeError as exc:
                assert "fork vietato" in str(exc)
            else:
                raise AssertionError("fork doveva essere bloccato")


def test_exception_frame_scrubbed():
    # punto 6: l'eccezione trattiene f_locals; serve wipe in finally + scrub
    canary = generate_runtime_canary(19)
    canary_s = canary.decode("ascii")
    s = SecretBytes.from_bytes(canary)
    caught_frame = None
    try:
        decoded = s.decode_at_boundary()
        try:
            raise ValueError(f"boom {decoded}")  # noqa: TRY301
        finally:
            # pattern obbligatorio: wipe+del in finally, MAI log traceback qui
            try:
                s.wipe()
            except Exception:
                pass
            try:
                decoded = "0" * len(decoded)
                del decoded
            except Exception:
                pass
    except ValueError as exc:
        import traceback as _tb

        caught_frame = _tb.extract_tb(exc.__traceback__)
        # il messaggio non deve finire nei log: qui verifichiamo che il Secret e' zerato
        assert s.is_zeroed()
        # scrub dei frame vivi (best-effort): cerca il frame con f_locals
        tb = exc.__traceback__
        while tb is not None:
            scrub_frame_locals(tb.tb_frame, canary_s)
            tb = tb.tb_next
        del exc
    gc.collect()
    # dopo scrub+wipe lo store del Secret e' pulito
    assert count_needle_in_stores(canary, s) == 0
    del s
    del canary
    gc.collect()


def test_mlock_puntuale_report():
    # punto 1: lock puntuale con report per-pagina, mai mlockall
    hyg = apply_process_hygiene()
    assert hyg.get("mlockall", "").startswith("non usato di proposito")
    assert hyg.get("policy", "").startswith("puntuale")
    buf = bytearray(b"0123456789ABCDEF")
    rep = lock_secret_region(buf)
    assert "locked" in rep and "bytes" in rep and rep["bytes"] == len(buf)
    assert "page_size" in rep and "detail" in rep
    del buf
    gc.collect()
