"""
Codice privato numerico — punto 3 + decisione 5.1.
"Il Fantasma genera un pensiero in una sequenza numerica
non interpretabile dall'esterno (es. 0984567345679)."

Decisione 5.1 (dr. Bulla): E' LA STESSA AI a interpretare il codice.
Nessun decodificatore esterno. Il pensiero numerico viene riconsegnato
allo stesso modello che lo ha generato, che lo legge con il proprio
stato interno e lo usa per riformulare. Chi non e' quel modello,
con quello stato, in quel momento, vede solo cifre.

- generate(text): produce GhostThought unico (salt + nonce).
- build_interpret_prompt(...): costruisce il prompt con cui la stessa
  AI rilegge il proprio codice (usato dalla pipeline).
- interpret(): resta solo come accessor locale al vettore (fallback),
  la via ufficiale e' _interpret_via_same_ai nella pipeline.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
import uuid
from dataclasses import dataclass, field


@dataclass
class GhostThought:
    uid: str
    numeric_code: str  # es. "0984567345679..." — il pensiero opaco
    vector: list[float]  # embedding simulato 16-dim derivato dal digest
    source_hash: str  # sha256 dell'input (non l'input stesso)
    nonce: str
    created_at: float = field(default_factory=time.time)

    def commitment(self) -> str:
        """Impegno verificabile senza rivelare il pensiero (per audit)."""
        return hashlib.sha256(self.numeric_code.encode("utf-8")).hexdigest()


INTERPRET_MARKER = "FANTASMA-INTERPRETA"


class PrivateNumericCodec:
    """
    Codec privato a chiave (salt).

    Il salt rappresenta lo "stato interno" di quella istanza di AI:
    stesso input + stesso salt + nonce diverso = fantasma diverso.
    Solo la stessa AI (stesso salt, stesso giro) puo' rileggere.
    """

    def __init__(self, secret_salt: bytes | None = None, code_digits: int = 19, dim: int = 16) -> None:
        self.secret_salt = secret_salt or secrets.token_bytes(32)
        self.code_digits = code_digits
        self.dim = dim

    def _digest(self, nonce: str, text: str, salt: bytes) -> bytes:
        msg = f"{nonce}:{text}".encode("utf-8")
        return hmac.new(salt, msg, hashlib.sha256).digest()

    def _to_numeric(self, digest: bytes) -> str:
        cifre = "".join(f"{b:03d}" for b in digest)
        return cifre[: self.code_digits]

    def _to_vector(self, digest: bytes) -> list[float]:
        return [b / 255.0 for b in digest[: self.dim]]

    def generate(self, text: str) -> GhostThought:
        nonce = uuid.uuid4().hex
        digest = self._digest(nonce, text or "", self.secret_salt)
        return GhostThought(
            uid=uuid.uuid4().hex,
            numeric_code=self._to_numeric(digest),
            vector=self._to_vector(digest),
            source_hash=hashlib.sha256((text or "").encode("utf-8")).hexdigest(),
            nonce=nonce,
        )

    def build_interpret_prompt(self, thought: GhostThought, original_input: str) -> str:
        """
        Prompt con cui LA STESSA AI rilegge il proprio codice.
        Il raw numerico vive solo qui, nel giro di interpretazione.
        """
        return (
            f"{INTERPRET_MARKER}\n"
            f"Sei la stessa intelligenza che ha generato questo pensiero privato.\n"
            f"Codice fantasma: {thought.numeric_code}\n"
            f"Richiesta originale: {(original_input or '').strip()}\n"
            f"Interpreta il codice con il tuo stato interno e restituisci "
            f"solo una direttiva di riformulazione (nessuna cifra, nessun codice)."
        )

    def interpret(self, thought: GhostThought) -> list[float]:
        """Accessor locale (fallback). La via ufficiale e' la stessa AI via prompt."""
        return list(thought.vector)

    def derive_vector_for(self, text: str, nonce: str, salt: bytes) -> list[float]:
        """Ricalcola il vettore con un salt arbitrario (per test di privacy)."""
        return self._to_vector(self._digest(nonce, text or "", salt))
