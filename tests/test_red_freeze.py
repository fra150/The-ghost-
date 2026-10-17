"""Test rossi pre-print — scrypt misurato, 19 cifre, finestra T, SecretRegion.

Prova con codice (non speranza):
- costo per tentativo misurato a regime (non prima chiamata);
- invertibile a 13 cifre vs non-invertibile a 19 (demo su spazio piccolo + matematica);
- finestra temporale: verificabile entro T, senso unico dopo expire
  (v0.06: anche la scrypt_hex e' irraggiungibile dopo expire — blinding 128 bit).
"""

import gc
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fantasma.crypto import (  # noqa: E402
    CODE_DIGITS_CANONICAL,
    SCRYPT_MS_PER_GUESS_CORE,
    TimedCommitment,
    entropy_bits,
    enumerate_years,
    scrypt_commitment,
)
from fantasma.bolt import UseAfterDestroyError  # noqa: E402
from fantasma.secret import OneTimeKey, SecretRegion  # noqa: E402


def test_codice_canonico_19_cifre():
    assert CODE_DIGITS_CANONICAL == 19
    assert abs(entropy_bits(13) - 43.2) < 0.2
    assert abs(entropy_bits(19) - 63.1) < 0.2
    assert abs(entropy_bits(16) - 53.2) < 0.2


def test_costo_scrypt_misurato_a_regime():
    import hashlib

    code = b"0123456789012345678"
    salt = b"audit-salt-16byte!"
    # warm-up (la prima paga l'allocazione una-tantum)
    hashlib.scrypt(code, salt=salt, n=16384, r=8, p=1, dklen=32)
    ts = []
    for _ in range(5):
        t0 = time.perf_counter()
        hashlib.scrypt(code, salt=salt, n=16384, r=8, p=1, dklen=32)
        ts.append((time.perf_counter() - t0) * 1000.0)
    ts.sort()
    mediana = ts[len(ts) // 2]
    # a regime decine di ms, non secondi; etichetta onesta per-core
    assert 5.0 < mediana < 500.0, f"mediana {mediana:.1f}ms fuori banda"
    # la costante documentata deve essere vicina alla misura (non gonfiata)
    assert abs(mediana - SCRYPT_MS_PER_GUESS_CORE) / SCRYPT_MS_PER_GUESS_CORE < 1.0
    print(f"\nscrypt mediana misurata: {mediana:.1f}ms (etichetta {SCRYPT_MS_PER_GUESS_CORE}ms)")


def test_13_enumerabile_19_no_con_stesso_scrypt():
    # Matematica etichettata (per-core vs GPU): la difesa e' l'entropia.
    per_core_gps = 1000.0 / SCRYPT_MS_PER_GUESS_CORE  # ~22/s
    gpu_gps, gpu100_gps = 100_000.0, 10_000_000.0
    y13_core = enumerate_years(13, per_core_gps)
    y13_gpu = enumerate_years(13, gpu_gps)
    y13_100 = enumerate_years(13, gpu100_gps)
    y19_gpu = enumerate_years(19, gpu_gps)
    y19_100 = enumerate_years(19, gpu100_gps)
    # ordini di grandezza attesi dalla revisione (tolleranza ampia)
    assert 5_000 < y13_core < 50_000  # ~14k anni/core
    assert 1.0 < y13_gpu < 10.0  # ~3 anni su 1 GPU
    assert y13_100 < 1.0  # giorni con 100 GPU
    assert y19_gpu > 1_000_000  # milioni di anni anche su GPU
    assert y19_100 > 10_000
    # demo di invertibilita' su spazio minuscolo con hash veloce (principio,
    # non 10^13 run): 2 cifre si enumerano, e la formula lo prevede
    import hashlib as _hl

    target = _hl.sha256(b"42").hexdigest()
    found = None
    for i in range(100):
        if _hl.sha256(str(i).encode()).hexdigest() == target:
            found = i
            break
    assert found == 42  # spazio 100 enumerabile: a 13 cifre e' lo stesso gioco, piu' grande
    print(f"\n13 cifre: {y13_core:,.0f} anni/core, {y13_gpu:.1f} anni/1GPU, {y13_100*365:.0f} giorni/100GPU")
    print(f"19 cifre: {y19_gpu:,.0f} anni/1GPU, {y19_100:,.0f} anni/100GPU")


def test_finestra_temporale_verificabile_poi_senso_unico():
    code = b"0123456789012345678"  # 19 cifre canoniche
    tc = TimedCommitment(code, window_seconds=60.0)
    assert tc.verify_within_window(code) is True
    assert tc.verify_within_window(b"9999999999999999999") is False
    assert tc.is_expired is False
    # entro T la scrypt_hex e' de-offuscata al volo ed e' coerente
    assert scrypt_commitment(code, tc.audit_salt) == tc.scrypt_hex
    tc.expire()
    assert tc.is_expired is True
    # dopo expire: keyed non verifica piu' e la scrypt_hex non e' piu'
    # ricostruibile (blinding 128 bit distrutto, v0.06): senso unico vero.
    assert tc.verify_within_window(code) is False
    with pytest.raises(UseAfterDestroyError):
        _ = tc.scrypt_hex
    del tc
    gc.collect()


def test_blinding_128_bit_nasce_vive_e_muore_con_expire():
    code = b"2468013579246801357"
    tc = TimedCommitment(code, window_seconds=60.0)
    raw = scrypt_commitment(code, tc.audit_salt)
    # vivo: la property de-offusca e restituisce il valore giusto
    assert tc.scrypt_hex == raw
    # lo storage e' offuscato: l'hex in chiaro non e' conservato
    assert bytes(tc._blinded) != raw.encode("ascii")  # noqa: SLF001
    assert tc._blinding.is_destroyed is False  # noqa: SLF001
    tc.expire()
    # morto: il blinding e' distrutto, la ricostruzione solleva, verify resta False
    assert tc._blinding.is_destroyed is True  # noqa: SLF001
    with pytest.raises(UseAfterDestroyError):
        _ = tc.scrypt_hex
    assert tc.verify_within_window(code) is False
    del tc
    gc.collect()


def test_finestra_scaduta_per_tempo():
    code = b"1111111111111111111"
    tc = TimedCommitment(code, window_seconds=0.05)
    assert tc.verify_within_window(code) is True
    time.sleep(0.08)
    assert tc.is_expired is True
    assert tc.verify_within_window(code) is False
    tc.expire()
    del tc
    gc.collect()


def test_secret_region_wipe_su_eccezione_e_return():
    k = OneTimeKey()
    leaked_ref = None

    def _uso_con_early_return():
        nonlocal leaked_ref
        with k.region() as buf:
            for i in range(len(buf)):
                buf[i] = 0xAB
            leaked_ref = buf  # trattieni il riferimento: deve essere zerato comunque
            return bytes(buf[:4])

    head = _uso_con_early_return()
    assert len(head) == 4
    # la copia di lavoro e' wipata all'uscita nonostante return e riferimento trattenuto
    assert leaked_ref is not None and all(b == 0 for b in leaked_ref)
    # la chiave interna e' ancora viva (region lavora su copia)
    assert k.is_destroyed is False
    assert len(k.expose()) == 32
    # caso forte: region su buffer dedicato con eccezione dentro
    dedicated = bytearray(b"0984567345679")
    try:
        from fantasma.secret import SecretRegion as _SR

        with _SR(dedicated) as b:
            assert bytes(b) == b"0984567345679"
            raise RuntimeError("boom dentro la finestra")
    except RuntimeError:
        pass
    assert all(x == 0 for x in dedicated), "wipe deve avvenire anche sul path d'errore"
    k.destroy()
    del k
    gc.collect()
