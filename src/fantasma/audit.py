"""
Audit esterno con hash-chain — punto 5.4.
"Se il Fantasma e' invisibile, come si fa a sapere che non sta barando?"

Trade-off strutturale implementato:
- MAI logghiamo numeric_code, vector, nonce o testo del pensiero;
- logghiamo solo commitment (sha256 del codice) + hash di input/output;
- chiunque puo' verificare la catena senza vedere il pensiero.

Privacy del Fantasma preservata, verificabilita' di esistenza/coerenza
preservata. Non risolve il paradosso, lo rende esplicito e controllabile.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field


@dataclass
class AuditEvent:
    seq: int
    ts: float
    kind: str  # input_received | gate_decision | ghost_activated | reformulated | output_produced | ghost_erased
    payload_hash: str  # hash del contenuto (mai il contenuto)
    prev_hash: str
    meta: dict = field(default_factory=dict)
    event_hash: str = ""

    def compute_hash(self) -> str:
        base = f"{self.seq}|{self.ts:.6f}|{self.kind}|{self.payload_hash}|{self.prev_hash}".encode()
        return hashlib.sha256(base).hexdigest()


class AuditLogger:
    """
    Hash-chain invariata (compatibile v0.01). Novita' v0.02:
    - payload dei ghost = scrypt (memory-hard), MAI HMAC nudo su 43 bit;
    - verifica keyed solo entro la finestra T via TimedCommitment (vedi crypto);
      paradosso risolto, non aggirato: 'verificabile entro T, senso unico dopo T'.
    v0.06: dopo expire chiave di finestra e blinding 128 bit sono distrutti;
      nemmeno la scrypt_hex e' ricostruibile (property -> UseAfterDestroyError).
    """
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []
        self._genesis = "FANTASMA-GENESIS-v0.1"

    @staticmethod
    def hash_text(text: str) -> str:
        return hashlib.sha256((text or "").encode("utf-8")).hexdigest()

    def log(self, kind: str, payload_hash: str, meta: dict | None = None) -> AuditEvent:
        prev = self.events[-1].event_hash if self.events else self._genesis
        ev = AuditEvent(
            seq=len(self.events),
            ts=time.time(),
            kind=kind,
            payload_hash=payload_hash,
            prev_hash=prev,
            meta=dict(meta or {}),
        )
        ev.event_hash = ev.compute_hash()
        self.events.append(ev)
        return ev

    def verify(self) -> bool:
        prev = self._genesis
        for i, ev in enumerate(self.events):
            if ev.seq != i:
                return False
            if ev.prev_hash != prev:
                return False
            if ev.event_hash != ev.compute_hash():
                return False
            prev = ev.event_hash
        return True

    def kinds(self) -> list[str]:
        return [e.kind for e in self.events]
