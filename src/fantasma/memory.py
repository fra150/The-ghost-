"""
Memoria effimera + cache offuscata + amnesia — decisioni 5.2 e 5.3.

Decisione 5.2 (dr. Bulla): il pensiero finisce in CACHE ma OFFUSCATO.
Il raw numerico non sta mai in cache. In cache va solo una forma
offuscata (shift delle cifre derivato dal salt = stato interno dell'AI).
Chi ruba la cache vede cifre che non significano nulla senza il salt.

Decisione 5.3 (dr. Bulla): dopo l'output NON serve ricordare.
Nessuna persistenza, nessun vector-DB. Amnesia di progetto:
alla fine del ciclo memoria effimera E cache sono vuote.

- EphemeralMemory: raw transient, vive solo nel giro (best-effort wipe).
- ObfuscatedCache: trattiene solo offuscato durante il giro, poi wipe.
"""

from __future__ import annotations

import gc
import hashlib
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .codec import GhostThought


def _offset_from_salt(salt: bytes) -> int:
    return sum(salt) % 10


def obfuscate_numeric(code: str, salt: bytes) -> str:
    """Offusca cifre con shift derivato dal salt (stato interno AI)."""
    off = _offset_from_salt(salt)
    return "".join(str((int(ch) + off) % 10) if ch.isdigit() else ch for ch in code)


def deobfuscate_numeric(obfuscated: str, salt: bytes) -> str:
    """Ripristina solo con lo stesso salt. Con salt sbagliato -> rumore."""
    off = _offset_from_salt(salt)
    return "".join(str((int(ch) - off) % 10) if ch.isdigit() else ch for ch in obfuscated)


@dataclass
class ObfuscatedTrace:
    uid_hash: str
    obfuscated_code: str  # MAI il raw
    commitment: str  # sha256 del raw (per audit, senza rivelarlo)
    source_hash: str
    ts: float = field(default_factory=time.time)


class EphemeralMemory:
    """Raw transient: vive solo per il giro di interpretazione."""

    def __init__(self) -> None:
        self._store: dict[str, GhostThought] = {}

    def put(self, thought: GhostThought) -> None:
        self._store[thought.uid] = thought

    def get(self, uid: str) -> GhostThought | None:
        return self._store.get(uid)

    def __len__(self) -> int:
        return len(self._store)

    def __contains__(self, uid: object) -> bool:
        return uid in self._store

    def forget(self, uid: str) -> bool:
        thought = self._store.get(uid)
        if thought is None:
            return False
        try:
            thought.numeric_code = "0" * len(thought.numeric_code)
            thought.vector = [0.0] * len(thought.vector)
            thought.nonce = "0" * len(thought.nonce)
        finally:
            self._store.pop(uid, None)
            gc.collect()
        return True

    def selective_reset(self) -> int:
        uids = list(self._store.keys())
        for uid in uids:
            self.forget(uid)
        gc.collect()
        return len(uids)


class ObfuscatedCache:
    """
    Cache offuscata: trattiene solo cifre offuscate durante il giro.
    Il raw non entra mai qui. A fine ciclo viene svuotata (amnesia 5.3).
    """

    def __init__(self, salt: bytes) -> None:
        self._salt = bytes(salt)
        self._store: dict[str, ObfuscatedTrace] = {}

    def seal(self, thought: GhostThought) -> ObfuscatedTrace:
        """Sigilla il pensiero in cache in forma offuscata. Non trattiene il raw."""
        uid_hash = hashlib.sha256(thought.uid.encode()).hexdigest()
        trace = ObfuscatedTrace(
            uid_hash=uid_hash,
            obfuscated_code=obfuscate_numeric(thought.numeric_code, self._salt),
            commitment=thought.commitment(),
            source_hash=thought.source_hash,
        )
        self._store[uid_hash] = trace
        return trace

    def get(self, uid_hash: str) -> ObfuscatedTrace | None:
        return self._store.get(uid_hash)

    def __len__(self) -> int:
        return len(self._store)

    def clear(self) -> int:
        n = len(self._store)
        for trace in self._store.values():
            trace.obfuscated_code = "0" * len(trace.obfuscated_code)
        self._store.clear()
        gc.collect()
        return n
