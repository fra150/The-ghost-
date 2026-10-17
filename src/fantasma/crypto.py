"""
Il Fantasma v0.02 — crypto.py
Crypto-shredding in sola stdlib + scrypt misurato + codice canonico 19 cifre
+ finestra temporale dichiarata.

Punti rossi chiusi con codice (revisione pre-print):
1. Numeri etichettati: scrypt N=2^14,r=8,p=1 ~44ms/tentativo su un core
   (mediana steady-state, non prima chiamata) = ~14.000 anni/core su 10^13.
   MA scrypt e' bandwidth-bound: su GPU il costo scende a pochi anni, con
   decine di GPU a giorni. Il numero per-core NON e' la difesa.
2. Leva vera = entropia: 13 cifre = 43,2 bit (enumerabile), 19 cifre = 63,1 bit
   (fuori portata anche a 100 GPU). Su 43 bit verificabile e non-invertibile
   sono mutuamente esclusivi: o alzi a 19 (senso unico vero) o dichiari la
   finestra T (verificabile entro T, senso unico dopo T). Qui entrambe.
   v0.06: la scrypt_hex in chiaro era l'ultimo residuo verificabile senza
   chiave; ora e' offuscata (blinding 128 bit) e il blinding muore con
   expire(). "Senso unico dopo T" vale ora anche sull'artefatto.
3. Chiave in buffer mutabile + SecretRegion: wipe per costruzione via ctypes,
   anche su eccezione/return. expose_mutable resta API basso livello.

Codice canonico: 19 cifre decimali, MAI intero (zero iniziale significativo).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass, field

from .secret import OneTimeKey

CODE_DIGITS_CANONICAL = 19  # 63,1 bit: fuori portata anche a 100 GPU
CODE_DIGITS_LEGACY = 13  # 43,2 bit: enumerabile, solo per test di invertibilita'

# Costo misurato steady-state (mediana su run a regime, non prima chiamata):
# N=2^14,r=8,p=1 -> ~44ms/tentativo/core -> ~14.000 anni/core su 10^13.
# Su GPU (bandwidth-bound): ~100k guess/s -> 13 cifre ~3,2 anni, 100 GPU ~12 giorni.
# A 19 cifre: 1 GPU ~3,2M anni, 100 GPU ~32k anni. La difesa e' l'entropia.
SCRYPT_N = 16384
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_MS_PER_GUESS_CORE = 44.0


def _keystream_into(key: bytes | bytearray, nonce: bytes, out: bytearray) -> None:
    """Riempie out con SHA256(key||nonce||ctr). Accetta bytearray (no copie str)."""
    ctr = 0
    pos = 0
    n = len(out)
    kb = bytes(key)
    while pos < n:
        h = hashlib.sha256(kb + bytes(nonce) + ctr.to_bytes(4, "big")).digest()
        take = min(len(h), n - pos)
        out[pos:pos + take] = h[:take]
        pos += take
        ctr += 1
    del kb


def seal_with_key(key: bytes | bytearray, plaintext: bytes | bytearray) -> tuple[bytes, bytes, bytes]:
    """
    encrypt-then-MAC stdlib. Ritorna (nonce12, ciphertext, tag32).
    Opera su bytearray quando possibile per restare wipabile.
    """
    nonce = secrets.token_bytes(12)
    pt = bytes(plaintext)
    ks = bytearray(len(pt))
    try:
        _keystream_into(key, nonce, ks)
        ct = bytes(a ^ b for a, b in zip(pt, bytes(ks)))
    finally:
        for i in range(len(ks)):
            ks[i] = 0x00
        del ks
    tag = hmac.new(bytes(key), nonce + ct, hashlib.sha256).digest()
    return nonce, ct, tag


def open_with_key(key: bytes | bytearray, nonce: bytes, ciphertext: bytes, tag: bytes) -> bytes:
    expected = hmac.new(bytes(key), bytes(nonce) + bytes(ciphertext), hashlib.sha256).digest()
    if not hmac.compare_digest(expected, bytes(tag)):
        raise ValueError("tag invalido: chiave distrutta/errata o blob manomesso.")
    ks = bytearray(len(ciphertext))
    try:
        _keystream_into(key, bytes(nonce), ks)
        return bytes(a ^ b for a, b in zip(bytes(ciphertext), bytes(ks)))
    finally:
        for i in range(len(ks)):
            ks[i] = 0x00
        del ks


def scrypt_commitment(code: bytes | bytearray, audit_salt: bytes, n: int = SCRYPT_N, r: int = SCRYPT_R, p: int = SCRYPT_P) -> str:
    """
    Impegno memory-hard, deterministico a parita' di salt (contestabile).
    ~44ms/tentativo su un core a regime. Su 43 bit resta enumerabile da
    avversario GPU: la difesa e' il codice a 19 cifre, non il KDF da solo.
    """
    return hashlib.scrypt(bytes(code), salt=bytes(audit_salt), n=n, r=r, p=p, dklen=32).hex()


def entropy_bits(n_digits: int) -> float:
    """Bit di entropia di un codice decimale a n cifre."""
    import math

    return n_digits * math.log2(10)


def enumerate_years(n_digits: int, guesses_per_sec: float) -> float:
    """Anni per enumerare 10^n_digits a guesses_per_sec."""
    return (10 ** n_digits) / float(guesses_per_sec) / 3600.0 / 24.0 / 365.25


class TimedCommitment:
    """
    Finestra temporale dichiarata (punto rosso 2b + Visione 'limiti temporali').
    - Entro T: verificabile via tag keyed (chiave di finestra viva) + scrypt;
    - Dopo T (expire): chiave di finestra E blinding distrutti con memset;
      resta solo l'artefatto cieco, senza via di ricostruzione.
    v0.06 (prerequisito paper r.117): la scrypt_hex non e' piu' un attributo
    in chiaro. Storage = hex XOR keystream da un blinding monouso di 128 bit;
    `scrypt_hex` e' una property che de-offusca al volo e solleva
    UseAfterDestroyError dopo expire (o su blinding distrutto). A 13 cifre
    l'audit e' verificabile entro T ma enumerabile; a 19 cifre e' a senso
    unico anche dopo.
    """

    def __init__(self, code: bytes | bytearray, window_seconds: float = 3600.0) -> None:
        from .secret import OneTimeKey as _OTK

        self._window_key = _OTK(32)
        self._blinding = _OTK(16)  # v0.06: blinding monouso 128 bit
        self.audit_salt = secrets.token_bytes(16)
        raw = scrypt_commitment(code, self.audit_salt)
        # storage offuscato: hex ASCII XOR keystream dal blinding
        ks = bytearray(len(raw))
        try:
            with self._blinding.region() as b_mut:
                _keystream_into(b_mut, self.audit_salt, ks)
            self._blinded = bytearray(a ^ b for a, b in zip(raw.encode("ascii"), bytes(ks)))
        finally:
            for i in range(len(ks)):
                ks[i] = 0x00
            del ks
        self.key_id = self._window_key.commitment[:16]
        self.expires_at = time.time() + float(window_seconds)
        self._expired = False
        self._tag = hmac.new(
            self._window_key.expose(), raw.encode("ascii"), hashlib.sha256
        ).hexdigest()
        del raw
        # wipa subito la copia esposta della chiave di finestra
        tmp = self._window_key.expose_mutable()
        for i in range(len(tmp)):
            tmp[i] = 0x00
        del tmp

    @property
    def scrypt_hex(self) -> str:
        """De-offusca al volo l'impegno. Dopo expire il blinding e' distrutto."""
        if self._blinding.is_destroyed:
            from .bolt import UseAfterDestroyError

            raise UseAfterDestroyError(
                "Blinding distrutto: l'impegno non e' piu' ricostruibile (senso unico)."
            )
        ks = bytearray(len(self._blinded))
        try:
            with self._blinding.region() as b_mut:
                _keystream_into(b_mut, self.audit_salt, ks)
            return bytes(a ^ b for a, b in zip(bytes(self._blinded), bytes(ks))).decode("ascii")
        finally:
            for i in range(len(ks)):
                ks[i] = 0x00
            del ks

    def verify_within_window(self, code: bytes | bytearray) -> bool:
        """True solo se entro T, chiave e blinding vivi, scrypt e tag coincidono."""
        if self._expired or self._window_key.is_destroyed or self._blinding.is_destroyed:
            return False
        if time.time() > self.expires_at:
            return False
        sha = self.scrypt_hex
        if scrypt_commitment(code, self.audit_salt) != sha:
            return False
        expect = hmac.new(
            self._window_key.expose(), sha.encode(), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expect, self._tag)

    def expire(self) -> None:
        """Chiude la finestra: memset chiave di finestra + blinding. Dopo, solo artefatto cieco."""
        try:
            try:
                self._window_key.destroy()
            finally:
                self._blinding.destroy()
        finally:
            self._expired = True

    @property
    def is_expired(self) -> bool:
        return self._expired or time.time() > self.expires_at


@dataclass
class SealedBlob:
    """Contenuto della cache v0.02: MAI plaintext, MAI grezzo."""
    nonce: bytes
    ciphertext: bytes
    tag: bytes
    audit_salt: bytes
    key_commitment: str
    plaintext_commitment: str  # scrypt, non HMAC nudo
    ts: float = field(default_factory=time.time)
    algo: str = "stdlib-encrypt-then-MAC-SHA256+HMAC-SHA256/scrypt-audit"

    def __repr__(self) -> str:
        return (
            f"<SealedBlob {self.algo} ct_len={len(self.ciphertext)} "
            f"key={self.key_commitment[:12]}… pt={self.plaintext_commitment[:12]}…>"
        )


class CryptoShredder:
    """
    Sigilla con chiave RANDOM monouso (non derivata), poi la distrugge con memset.

    Corollario misurato: se la chiave fosse derivata da salt+nonce conservati,
    il destroy sarebbe finto (resta lo stampo). Qui non c'e' materiale di
    derivazione da conservare: la chiave nasce random e muore con memset.
    """

    def __init__(self) -> None:
        self._key = OneTimeKey(32)

    @property
    def key_commitment(self) -> str:
        return self._key.commitment

    @property
    def is_destroyed(self) -> bool:
        return self._key.is_destroyed

    def seal(self, plaintext: bytes | bytearray) -> SealedBlob:
        """Sigilla usando SecretRegion: wipe per costruzione, anche su eccezione."""
        if self._key.is_destroyed:
            from .bolt import UseAfterDestroyError as _BoltErr

            raise _BoltErr("Shredder distrutto: il catenaccio e' chiuso (non sigilla piu').")
        pt = bytes(plaintext)
        audit_salt = secrets.token_bytes(16)
        try:
            with self._key.region() as k_mut:
                nonce, ct, tag = seal_with_key(k_mut, pt)
            pt_comm = scrypt_commitment(pt, audit_salt)
            return SealedBlob(
                nonce=nonce,
                ciphertext=ct,
                tag=tag,
                audit_salt=audit_salt,
                key_commitment=self._key.commitment,
                plaintext_commitment=pt_comm,
            )
        finally:
            ba = bytearray(pt)
            for i in range(len(ba)):
                ba[i] = 0x00
            del ba
            del pt
            try:
                if isinstance(plaintext, bytearray):
                    for i in range(len(plaintext)):
                        plaintext[i] = 0x00
            except Exception:
                pass

    def open(self, blob: SealedBlob) -> bytes:
        if self._key.is_destroyed:
            from .bolt import UseAfterDestroyError as _BoltErr

            raise _BoltErr("Chiave distrutta: blob irrecuperabile (e' la garanzia, catenaccio chiuso).")
        with self._key.region() as k_mut:
            return open_with_key(k_mut, blob.nonce, blob.ciphertext, blob.tag)

    def destroy(self) -> str:
        """Memset del buffer chiave + flag. Ritorna key_commitment per audit."""
        return self._key.destroy()
