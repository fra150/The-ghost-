"""
Il Fantasma v0.04 — bolt.py ("blocco del catenaccio", parte software).

Scope v0.04 (dopo il P0), con tre correzioni vincolanti:

1. La ricevuta NON contiene nulla derivato dal codice (niente scrypt/hash
   del codice: sarebbe un secondo commitment a bassa entropia, superficie
   d'attacco in piu'). Solo: uid_hash, nonce casuale, timestamp, hash
   della voce precedente (hash-chain). Niente codice, niente commitment.
2. NON e' una "prova di eliminazione": e' un REGISTRO di cancellazione con
   integrita' a catena, attestato dallo stesso processo che dichiara di
   aver cancellato. Una prova richiederebbe testimone indipendente o
   hardware attestato (TPM/TEE) -> supervisione indipendente della v1.0.
3. Niente mprotect(PROT_NONE) qui: un bytearray vive in arene pymalloc
   condivise, proteggere la pagina ucciderebbe i vicini e un accesso
   sbagliato e' SIGSEGV (morte del processo, non eccezione Python).
   mprotect su regione mmap dedicata + worker spawn = esperimento v1.0.

Cosa FA (onesto): macchina a stati esplicita VIVO -> SIGILLATO -> DISTRUTTO,
errore tipizzato su ogni uso dopo la distruzione, wipe idempotente ma
registrato. Protegge dai bug del nostro codice (riuso silenzioso), NON da
un attaccante con accesso alla memoria (che ignora i blocchi a livello API).
Misura associata: tasso di rilevazione dei riusi dopo distruzione (test).
"""

from __future__ import annotations

import hashlib
import secrets
import time
from dataclasses import dataclass, field
from enum import Enum


class BoltState(str, Enum):
    VIVO = "vivo"
    SIGILLATO = "sigillato"
    DISTRUTTO = "distrutto"


class UseAfterDestroyError(ValueError):
    """Uso dopo la distruzione: il catenaccio e' chiuso.

    Sottoclasse di ValueError per compatibilita' con il codice v0.02/v0.03
    (chi cattura ValueError continua a funzionare, chi vuole il blocco
    tipizzato cattura questa).
    """


def _entry_hash(prev_hash: str, uid_hash: str, nonce_hex: str, ts: float) -> str:
    body = f"{prev_hash}|{uid_hash}|{nonce_hex}|{ts:.6f}".encode("utf-8")
    return hashlib.sha256(body).hexdigest()


@dataclass(frozen=True)
class BoltReceipt:
    """Ricevuta di cancellazione. Nessun campo deriva dal codice."""

    uid_hash: str
    nonce_hex: str
    ts: float
    prev_hash: str
    entry_hash: str
    n: int = 0  # posizione nella catena

    def to_dict(self) -> dict:
        return {"uid_hash": self.uid_hash, "nonce_hex": self.nonce_hex,
                "ts": self.ts, "prev_hash": self.prev_hash,
                "entry_hash": self.entry_hash, "n": self.n}


class BoltRegistry:
    """Registro di cancellazione con integrita' a catena (per pipeline).

    Una istanza per pipeline: le ricevute di process() successivi si
    concatenano (prev_hash). Idempotente per uid: il secondo bolt dello
    stesso uid restituisce la stessa ricevuta con is_first=False e conta
    il tentativo (riusi rilevati, non silenziati).
    """

    GENESIS = "GENESI"

    def __init__(self) -> None:
        self._entries: list[BoltReceipt] = []
        self._by_uid: dict[str, BoltReceipt] = {}
        self._attempts: dict[str, int] = {}

    def __len__(self) -> int:
        return len(self._entries)

    def bolt(self, uid_hash: str) -> tuple[BoltReceipt, bool]:
        uid_hash = str(uid_hash)
        self._attempts[uid_hash] = self._attempts.get(uid_hash, 0) + 1
        if uid_hash in self._by_uid:
            return self._by_uid[uid_hash], False
        prev = self._entries[-1].entry_hash if self._entries else self.GENESIS
        receipt = BoltReceipt(
            uid_hash=uid_hash,
            nonce_hex=secrets.token_bytes(16).hex(),
            ts=time.time(),
            prev_hash=prev,
            entry_hash="",
            n=len(self._entries),
        )
        fixed = BoltReceipt(
            uid_hash=receipt.uid_hash, nonce_hex=receipt.nonce_hex,
            ts=receipt.ts, prev_hash=receipt.prev_hash,
            entry_hash=_entry_hash(prev, uid_hash, receipt.nonce_hex, receipt.ts),
            n=receipt.n,
        )
        self._entries.append(fixed)
        self._by_uid[uid_hash] = fixed
        return fixed, True

    def attempts(self, uid_hash: str) -> int:
        return self._attempts.get(str(uid_hash), 0)

    def find(self, uid_hash: str) -> BoltReceipt | None:
        return self._by_uid.get(str(uid_hash))

    def verify_chain(self) -> bool:
        prev = self.GENESIS
        for i, r in enumerate(self._entries):
            if r.prev_hash != prev or r.n != i:
                return False
            if r.entry_hash != _entry_hash(r.prev_hash, r.uid_hash, r.nonce_hex, r.ts):
                return False
            prev = r.entry_hash
        return True
