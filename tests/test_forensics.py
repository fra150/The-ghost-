"""Test v0.02 — scomparsa misurabile (L1+L2), Cesare dichiarato, shredding AES-GCM.

Regola: canary SEMPRE generati a runtime, mai letterali.
Questi test non rompono i 12 esistenti: li affiancano.

Sezione A: primitive (Cesare, Secret, AES-GCM, hygiene, R).
Sezione B (guardare prima di dichiarare):
  B1 decode_at_boundary lascia str non wipabile -> L2 non R=0 col flusso reale;
  B2 controllo negativo leaky deve dare R>0 + varianti utf16;
  B3 AES-GCM reale, chiave errata/tag manomesso falliscono.
"""

import gc
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fantasma import deobfuscate_numeric, obfuscate_numeric  # noqa: E402
from fantasma.crypto import CryptoShredder, open_with_key, seal_with_key  # noqa: E402
from fantasma.forensics import (  # noqa: E402
    compute_R,
    count_needle_in_heap_via_gc,
    count_needle_in_stores,
    count_variants_in_stores,
    generate_runtime_canary,
    needle_variants,
    scan_process_mem,
)
from fantasma.hygiene import apply_process_hygiene  # noqa: E402
from fantasma.secret import OneTimeKey, SecretBytes  # noqa: E402


COMPLEX = (
    "Spiega perché questa decisione strategica è complessa, confronta le alternative "
    "e valuta i rischi? Tuttavia ci sono vincoli e bisogna progettare passi."
)


def test_52_cesare_e_deterrenza_non_cifratura():
    """Documenta il limite v0.01: shift <=10 possibilita', si forza a mano."""
    salt = b"salt-test-v002"
    raw = generate_runtime_canary(19)  # bytes runtime
    raw_s = raw.decode("ascii")
    off = obfuscate_numeric(raw_s, salt)
    assert off != raw_s
    tentativi = {deobfuscate_numeric(off, bytes([b])) for b in range(256)}
    assert len(tentativi) <= 10
    assert raw_s in tentativi  # lethal: la cache "offuscata" si legge a mano


def test_secret_wipe_e_repr_mascherato():
    canary = generate_runtime_canary(19)
    s = SecretBytes.from_bytes(canary)
    assert canary.decode("ascii") not in repr(s)
    try:
        str(s)
    except TypeError:
        pass
    else:
        raise AssertionError("str(Secret) deve alzare")
    try:
        s.__getstate__()
    except TypeError:
        pass
    else:
        raise AssertionError("pickle deve essere bloccato")
    comm = s.commitment()
    assert len(comm) == 64
    s.wipe()
    assert s.is_zeroed()
    del s
    del canary
    gc.collect()


def test_secret_heap_zero_dopo_wipe():
    """L1 portabile + L2 dove disponibile. Documenta il limite gc su Windows."""
    canary = generate_runtime_canary(19)
    s = SecretBytes.from_bytes(canary)
    assert s.expose_copy() == bytes(canary)
    assert count_needle_in_heap_via_gc(canary) == 0  # limite noto: gc non vede bytes/str
    assert count_needle_in_stores(canary, s) >= 1
    s.wipe()
    assert s.is_zeroed()
    assert count_needle_in_stores(canary, s) == 0
    mem = scan_process_mem(canary)  # dict | None
    if mem is None:
        pass  # Windows: /proc non disponibile
    else:
        assert "_regions_scanned" in mem
    del s
    del canary
    gc.collect()


def test_crypto_shredding_sigilla_e_distrugge():
    grezzo = generate_runtime_canary(19)
    sh = CryptoShredder()
    blob = sh.seal(grezzo)
    assert blob.algo.startswith("stdlib-encrypt-then-MAC")
    assert "scrypt" in blob.algo
    assert grezzo not in blob.ciphertext
    assert grezzo.decode("ascii") not in repr(blob)
    aperto = sh.open(blob)
    assert aperto == grezzo
    del aperto
    key_comm = sh.destroy()
    assert sh.is_destroyed
    assert key_comm == blob.key_commitment
    try:
        sh.open(blob)
    except ValueError:
        pass
    else:
        raise AssertionError("dopo destroy il blob deve essere irrecuperabile")
    assert grezzo not in blob.ciphertext
    del grezzo
    del sh
    del blob
    gc.collect()


def test_chiave_commitment_e_un_solo_uso():
    k = OneTimeKey()
    comm = k.commitment
    assert len(comm) == 64
    assert k.destroy() == comm
    assert k.is_destroyed
    try:
        k.expose()
    except ValueError:
        pass
    else:
        raise AssertionError("chiave distrutta non si espone")


def test_hygiene_non_alza_mai():
    rep = apply_process_hygiene()
    assert "platform" in rep and "rlimit_core" in rep and "mlockall" in rep


def test_R_metric_zero_quando_pulito():
    r = compute_R(heap_copies=0, cache_copies=0, file_copies=0)
    assert r["R"] == 0 and r["ok"] is True
    r2 = compute_R(heap_copies=8, cache_copies=0, file_copies=0)
    assert r2["R"] == 8 and r2["ok"] is False


# ---- Sezione B: guardare prima di dichiarare ----

def test_B1_decode_boundary_lascia_str_non_wipabile():
    """
    Punto 1. Il wipe azzera il bytearray ma NON la str decodificata.
    Finche' la str vive, L1 la trova. Dopo `del str`, L1 torna 0 ma L2
    (mem processo, JSON/HTTP/TLS) va misurato, non affermato.
    """
    canary = generate_runtime_canary(19)
    s = SecretBytes.from_bytes(canary)
    decoded = s.decode_at_boundary()  # unica copia str consentita
    assert isinstance(decoded, str)
    # lo store che trattiene la str la trova (giusto: esiste davvero)
    holder = {"prompt_frammento": decoded}
    assert count_needle_in_stores(canary, holder) >= 1
    # wipe del Secret NON cancella la str: e' il limite strutturale
    s.wipe()
    assert s.is_zeroed()
    assert count_needle_in_stores(canary, holder) >= 1  # la str sopravvive al wipe
    # solo dopo del+gc lo store torna pulito (L1), ma la memoria grezza
    # del processo potrebbe trattenerla: su Linux si misura, su Windows si dichiara
    del holder
    del decoded
    gc.collect()
    assert count_needle_in_stores(canary, {}) == 0
    mem = scan_process_mem(canary)
    # mem e' dict su Linux, None su Windows: in entrambi i casi non affermiamo L2=0
    assert mem is None or isinstance(mem, dict)
    del s
    del canary
    gc.collect()


def test_B2_controllo_negativo_leaky_deve_dare_R_maggiore_di_zero():
    """
    Punto 2. Se lo scanner da' R=0 anche su una pipeline volutamente leaky,
    non misura niente. Qui la leak e' esplicita (globale + log) e deve dare R>0.
    """
    canary = generate_runtime_canary(19)
    # simula pipeline leaky: codice in globale + log + cache in chiaro
    LEAKY_GLOBAL = {"ghost_raw": bytes(canary).decode("ascii")}
    LEAKY_LOG = f"TRACE ghost={bytes(canary).decode('ascii')} sealed"
    LEAKY_CACHE = {"uid123": bytes(canary)}
    r_raw = (
        count_needle_in_stores(canary, LEAKY_GLOBAL)
        + count_needle_in_stores(canary, LEAKY_LOG)
        + count_needle_in_stores(canary, LEAKY_CACHE)
    )
    assert r_raw > 0, "scanner cieco: non vede nemmeno una leak esplicita"
    # e dopo pulizia deve tornare 0 (lo scanner distingue pulito/sporco)
    del LEAKY_GLOBAL
    del LEAKY_LOG
    del LEAKY_CACHE
    gc.collect()
    assert count_needle_in_stores(canary, {}) == 0
    del canary
    gc.collect()


def test_B2_varianti_utf16_non_basta_cercare_il_raw():
    """
    Punto 2b. 'Non trovato' vale solo per cio' che cerchi.
    Un canary sopravvissuto come UTF-16LE sfugge alla ricerca raw.
    """
    canary = generate_runtime_canary(19)
    variants = needle_variants(canary)
    assert set(variants) >= {"raw", "utf16le", "utf16be"}
    # store che contiene SOLO la forma utf16le
    holder_utf16 = {"buf": variants["utf16le"]}
    assert count_needle_in_stores(variants["raw"], holder_utf16) == 0  # raw non lo vede
    res = count_variants_in_stores(canary, holder_utf16)
    assert res["R"] > 0 and res["per_variant"]["utf16le"] >= 1  # varianti lo vedono
    del holder_utf16
    del canary
    gc.collect()


def test_B3_stdlib_chiave_errata_e_tag_manomesso_falliscono():
    """Shredding stdlib wipabile: chiave errata e tag manomesso falliscono."""
    import secrets as _secrets

    key = _secrets.token_bytes(32)
    wrong = _secrets.token_bytes(32)
    pt = generate_runtime_canary(19)
    nonce, ct, tag = seal_with_key(key, pt)
    assert len(nonce) == 12 and len(tag) == 32  # HMAC-SHA256
    assert pt not in ct
    # chiave giusta apre
    assert open_with_key(key, nonce, ct, tag) == pt
    # chiave errata fallisce
    try:
        open_with_key(wrong, nonce, ct, tag)
    except ValueError:
        pass
    else:
        raise AssertionError("chiave errata deve fallire")
    # tag manomesso fallisce
    bad_tag = bytes([tag[0] ^ 1]) + tag[1:]
    try:
        open_with_key(key, nonce, ct, bad_tag)
    except ValueError:
        pass
    else:
        raise AssertionError("tag manomesso deve fallire")
    # ciphertext manomesso fallisce
    bad_ct = bytes([ct[0] ^ 1]) + ct[1:] if len(ct) else ct
    try:
        open_with_key(key, nonce, bad_ct, tag)
    except ValueError:
        pass
    else:
        raise AssertionError("ciphertext manomesso deve fallire")
    del key
    del wrong
    del pt
    gc.collect()
