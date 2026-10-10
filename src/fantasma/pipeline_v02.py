"""
Il Fantasma v0.02 — pipeline_v02.py
Cablaggio codec+memory dietro la STESSA interfaccia di pipeline.py.

Differenze rispetto a v0.01:
- il grezzo nasce come BYTES e vive in SecretBytes (mai str tranne 1 decode);
- la cache contiene solo SealedBlob AES-256-GCM (mai grezzo, mai Cesare);
- amnesia = wipe Secret + destroy chiave (crypto-shredding) + clear store;
- audit solo commitment (ghost sha, key commitment, output hash).

Punto delicato dichiarato (vedi SecretBytes.decode_at_boundary):
la decode a str per la stessa-AI crea copie immutabili (str/JSON/HTTP/TLS)
non wipabili. L1 si misura negli store, L2 si misura con scan_process_mem
su Linux. Nessun claim finche' non misurato.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable

from .audit import AuditLogger
from .codec import INTERPRET_MARKER
from .crypto import CryptoShredder
from .gate import HeuristicGate
from .ghost_window import ghost_window
from .hygiene import apply_process_hygiene, lock_secret_region
from .secret import SecretBytes


def default_mock_llm_v02(prompt: str) -> str:
    s = (prompt or "").strip()
    if not s:
        return "Output finale: (input vuoto.)"
    if INTERPRET_MARKER in s:
        cifre = "".join(ch for ch in s if ch.isdigit())
        try:
            totale = sum(int(c) for c in cifre) if cifre else 0
        except ValueError:
            totale = 0
        resto = totale % 3
        if resto == 0:
            return "Direttiva interna: chiarisci obiettivo, vincoli e criteri di successo."
        if resto == 1:
            return "Direttiva interna: scomponi in passi piccoli e verificabili, evidenzia ambiguità."
        return "Direttiva interna: riformula in modo neutro e operativo."
    head = s[:220].replace("\n", " ")
    return f"Output finale (da input riformulato): {head}"


def _hmac_digest(nonce: str, text: str, salt: bytes) -> bytes:
    return hmac.new(salt, f"{nonce}:{text}".encode("utf-8"), hashlib.sha256).digest()


def _digest_to_numeric_bytes(digest: bytes, n_digits: int = 19) -> bytes:
    cifre = "".join(f"{b:03d}" for b in digest)
    return cifre[:n_digits].encode("ascii")


@dataclass
class FantasmaResultV02:
    output: str
    ghost_activated: bool
    reformulated_input: str
    gate_reason: str
    ghost_commitment: str | None
    key_commitment: str | None
    audit_ok: bool
    memory_empty_after: bool
    cache_empty_after: bool
    used_same_ai: bool = False
    algo: str = "stdlib-encrypt-then-MAC-SHA256+HMAC-SHA256/scrypt-audit"
    hygiene: dict = field(default_factory=dict)
    meta: dict = field(default_factory=dict)


class FantasmaPipelineV02:
    """Stessa interfaccia .process() della v0.01, interno v0.02."""

    def __init__(
        self,
        gate: HeuristicGate | None = None,
        secret_salt: bytes | None = None,
        audit: AuditLogger | None = None,
        llm_fn: Callable[[str], str] | None = None,
    ) -> None:
        self.gate = gate or HeuristicGate()
        self.salt = secret_salt or secrets.token_bytes(32)
        self.audit = audit or AuditLogger()
        self.llm_fn = llm_fn or default_mock_llm_v02
        self.hygiene_report = apply_process_hygiene()
        # store applicativi L1: tengono solo Secret (transient) e blob (sealed)
        self._live_secrets: dict[str, SecretBytes] = {}
        self._sealed: dict[str, object] = {}

    def process(self, user_input: str) -> FantasmaResultV02:
        testo = user_input or ""
        self.audit.log("input_received", AuditLogger.hash_text(testo))
        decisione = self.gate.should_activate(testo)
        self.audit.log(
            "gate_decision",
            AuditLogger.hash_text(decisione.reason),
            meta={"active": decisione.active, "score": decisione.score},
        )
        if not decisione.active:
            out = self.llm_fn(testo)
            self.audit.log("output_produced", AuditLogger.hash_text(out), meta={"ghost": False})
            return FantasmaResultV02(
                output=out,
                ghost_activated=False,
                reformulated_input=testo,
                gate_reason=decisione.reason,
                ghost_commitment=None,
                key_commitment=None,
                audit_ok=self.audit.verify(),
                memory_empty_after=len(self._live_secrets) == 0,
                cache_empty_after=len(self._sealed) == 0,
                used_same_ai=False,
                hygiene=self.hygiene_report,
            )

        # 1. genera grezzo come BYTES, mai str — dentro la finestra no-fork
        with ghost_window():
            nonce = uuid.uuid4().hex
            digest = _hmac_digest(nonce, testo, self.salt)
            raw_bytes = _digest_to_numeric_bytes(digest)
            uid = uuid.uuid4().hex
            secret = SecretBytes.from_bytes(raw_bytes)
            # mlock puntuale sulla regione (punto 1): report per-pagina
            # Il report dice 'regione designata protetta', NON 'nessuna copia in swap'.
            try:
                self._last_lock = lock_secret_region(secret._buf)  # noqa: SLF001
                self.hygiene_report["last_lock"] = self._last_lock
            except Exception:
                self._last_lock = {"locked": False, "detail": "lock non riuscito"}
                self.hygiene_report["last_lock"] = self._last_lock
            del digest
            raw_bytes = b"\x00" * len(raw_bytes)
            del raw_bytes
            self._live_secrets[uid] = secret
            impegno = secret.commitment()
            uid_hash = hashlib.sha256(uid.encode()).hexdigest()
            self.audit.log("ghost_activated", impegno, meta={"uid_hash": uid_hash})

            # 2. STESSA AI: un'unica decode al boundary (punto 6: finally+no traceback)
            decoded = secret.decode_at_boundary()
            interpretation = ""
            try:
                prompt = (
                    f"{INTERPRET_MARKER}\n"
                    f"Sei la stessa intelligenza che ha generato questo pensiero privato.\n"
                    f"Codice fantasma: {decoded}\n"
                    f"Richiesta originale: {testo.strip()}\n"
                    f"Interpreta il codice con il tuo stato interno e restituisci "
                    f"solo una direttiva di riformulazione (nessuna cifra, nessun codice)."
                )
                decoded = "0" * len(decoded)
                del decoded
                interpretation = self.llm_fn(prompt)
                self.audit.log("ghost_interpreted", AuditLogger.hash_text(interpretation))
                prompt = "0" * len(prompt)
                del prompt
            except Exception:
                # MAI loggare traceback dentro la finestra (punto 6); wipe e propaga
                try:
                    secret.wipe()
                except Exception:
                    pass
                self._live_secrets.pop(uid, None)
                raise
            finally:
                # se decoded sopravvive all'eccezione, azzeralo qui (frame scrub best-effort)
                try:
                    if "decoded" in dir():
                        del decoded
                except Exception:
                    pass

            # 3. sigilla il grezzo in AES-GCM (cache = solo blob), poi wipe raw
            shredder = CryptoShredder()
            try:
                raw_for_seal = secret.expose_copy()
                try:
                    blob = shredder.seal(raw_for_seal)
                finally:
                    ba = bytearray(raw_for_seal)
                    for i in range(len(ba)):
                        ba[i] = 0x00
                    del ba
                    del raw_for_seal
                self._sealed[uid_hash] = blob
                self.audit.log(
                    "cached_sealed",
                    hashlib.sha256(blob.ciphertext).hexdigest(),
                    meta={"algo": blob.algo, "key_commitment": shredder.key_commitment},
                )
                key_comm = shredder.key_commitment
            finally:
                pass

            # wipe memoria effimera (L1) sempre, anche in caso di errore sopra
            try:
                secret.wipe()
            finally:
                self._live_secrets.pop(uid, None)

        # 4. riformula + output finale (mai cifre)
        riformulato = f"{interpretation.strip()}\nRichiesta originale: {testo.strip()}"
        self.audit.log("reformulated", AuditLogger.hash_text(riformulato))
        del interpretation
        out = self.llm_fn(riformulato)
        self.audit.log("output_produced", AuditLogger.hash_text(out), meta={"ghost": True})

        # 5. amnesia totale: distruggi CHIAVE (shredding), svuota sealed
        shredder.destroy()
        self._sealed.clear()
        self.audit.log("ghost_erased", AuditLogger.hash_text(uid + ":erased"))

        # cancella residui locali
        del shredder
        del secret

        return FantasmaResultV02(
            output=out,
            ghost_activated=True,
            reformulated_input=riformulato,
            gate_reason=decisione.reason,
            ghost_commitment=impegno,
            key_commitment=key_comm,
            audit_ok=self.audit.verify(),
            memory_empty_after=len(self._live_secrets) == 0,
            cache_empty_after=len(self._sealed) == 0,
            used_same_ai=True,
            hygiene=self.hygiene_report,
            meta={"uid_hash": uid_hash},
        )
