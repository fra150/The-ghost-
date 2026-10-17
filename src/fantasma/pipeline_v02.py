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
from .bolt import BoltRegistry
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
        cover_pii: bool = False,
    ) -> None:
        self.gate = gate or HeuristicGate()
        self.salt = secret_salt or secrets.token_bytes(32)
        self.audit = audit or AuditLogger()
        self.llm_fn = llm_fn or default_mock_llm_v02
        self.cover_pii = bool(cover_pii)
        self.hygiene_report = apply_process_hygiene()
        # store applicativi L1: tengono solo Secret (transient) e blob (sealed)
        self._live_secrets: dict[str, SecretBytes] = {}
        self._sealed: dict[str, object] = {}
        # v0.04 catenaccio: registro di cancellazione con integrita' a catena
        # (una istanza per pipeline: le ricevute si concatenano tra process()).
        self.bolts = BoltRegistry()

    def process(self, user_input: str) -> FantasmaResultV02:
        """Punto d'ingresso. Con cover_pii=True l'input e' coperto pre-CoT
        (solo placeholder al modello) e l'output e' ripristinato in locale;
        il mapping e' wipato e inchiodato al registro anche sui path d'errore."""
        cover = None
        if self.cover_pii:
            from .pii_cover import cover_text as _cover_text

            _res = _cover_text(user_input or "")
            _uid = hashlib.sha256(_res.covered.encode("utf-8")).hexdigest()
            cover = {"mapping": _res.mapping, "report": _res.report,
                     "uid": _uid, "work_text": _res.covered}
            self.audit.log("cover_applied",
                           AuditLogger.hash_text(_res.covered),
                           meta={"report": _res.report})
        try:
            return self._process_inner(user_input, _cover=cover)
        except Exception:
            if cover is not None:
                try:
                    cover["mapping"].wipe()
                except Exception:
                    pass
            raise

    def _cover_finish(self, out_covered: str, reform_covered: str,
                      cover: dict) -> tuple[str, str, dict]:
        """Restore in locale + residual scan sul coperto + bolt + wipe."""
        mp = cover["mapping"]
        try:
            residual = mp.values_present_in(out_covered)
            out = mp.restore(out_covered)
            reform = mp.restore(reform_covered)
            receipt, first = self.bolts.bolt("cover:" + cover["uid"])
            self.audit.log("cover_restored",
                           AuditLogger.hash_text(out_covered),
                           meta={"residual_n": len(residual)})
            self.audit.log("cover_bolted", receipt.entry_hash,
                           meta={"uid_hash": "cover:" + cover["uid"],
                                 "n": receipt.n, "first": first})
            meta = {"cover": True, "cover_report": cover["report"],
                    "cover_residual_n": len(residual),
                    "cover_residual": residual,
                    "bolt_cover": receipt.to_dict(),
                    "bolt_cover_first": first}
            return out, reform, meta
        finally:
            try:
                mp.wipe()
            except Exception:
                pass

    def _process_inner(self, user_input: str, _cover=None) -> FantasmaResultV02:
        testo = user_input or ""
        # Con cover attiva il modello vede solo il testo coperto; i valori veri
        # restano nel mapping e rientrano solo nel _cover_finish finale.
        work_text = testo
        if _cover is not None:
            work_text = _cover["work_text"]
        self.audit.log("input_received", AuditLogger.hash_text(work_text))
        decisione = self.gate.should_activate(work_text)
        self.audit.log(
            "gate_decision",
            AuditLogger.hash_text(decisione.reason),
            meta={"active": decisione.active, "score": decisione.score},
        )
        if not decisione.active:
            out_covered = self.llm_fn(work_text)
            if _cover is not None:
                out, reform, cover_meta = self._cover_finish(out_covered, work_text, _cover)
                return FantasmaResultV02(
                    output=out,
                    ghost_activated=False,
                    reformulated_input=reform,
                    gate_reason=decisione.reason,
                    ghost_commitment=None,
                    key_commitment=None,
                    audit_ok=self.audit.verify(),
                    memory_empty_after=len(self._live_secrets) == 0,
                    cache_empty_after=len(self._sealed) == 0,
                    used_same_ai=False,
                    hygiene=self.hygiene_report,
                    meta=cover_meta,
                )
            self.audit.log("output_produced", AuditLogger.hash_text(out_covered), meta={"ghost": False})
            return FantasmaResultV02(
                output=out_covered,
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
            digest = _hmac_digest(nonce, work_text, self.salt)
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
            # v0.04: prompt rigido condiviso + guard allowlist con 1 retry + fallback.
            decoded = secret.decode_at_boundary()
            interpretation = ""
            guard_report: dict = {}
            try:
                from .reform_guard import ReformulationGuard as _Guard
                from .reform_guard import build_call1_prompt as _build_p1
                _guard = _Guard()
                _code_display = decoded
                prompt = _build_p1(_code_display, work_text)
                _code_display = "0" * len(_code_display)
                del _code_display
                decoded = "0" * len(decoded)
                del decoded
                interpretation = self.llm_fn(prompt)
                self.audit.log("ghost_interpreted", AuditLogger.hash_text(interpretation))
                _rep = _guard.validate_with_report(interpretation, work_text)
                guard_report = _rep
                if not _rep["ok"]:
                    # 1 retry su Call-1, mai passare sporco a Call-2
                    self.audit.log("leak_rejected_retry", AuditLogger.hash_text(_rep.get("reason", "")))
                    interpretation = self.llm_fn(prompt)
                    self.audit.log("ghost_interpreted_retry", AuditLogger.hash_text(interpretation))
                    _rep2 = _guard.validate_with_report(interpretation, work_text)
                    guard_report = _rep2
                    if not _rep2["ok"]:
                        raise ValueError(f"leak persistente: {_rep2.get('reason', '')}")
                prompt = "0" * len(prompt)
                del prompt
            except Exception as _leak_exc:
                # MAI loggare traceback dentro la finestra (punto 6); wipe e propaga
                # v0.04: pulizia frame best-effort limitata, mai su frame attivi.
                try:
                    from .ghost_window import scrub_traceback as _scrub
                    import sys as _sys
                    _exc = _sys.exc_info()[1]
                    if _exc is not None:
                        _scrub(_exc)
                except Exception:
                    pass
                try:
                    secret.wipe()
                except Exception:
                    pass
                self._live_secrets.pop(uid, None)
                # v0.04: leak persistente -> fallback Direct pulito, contato a parte.
                if "leak persistente" in str(_leak_exc):
                    self.audit.log("leak_fallback_direct",
                                   AuditLogger.hash_text(str(guard_report.get("reason", ""))[:200]))
                    out_covered = self.llm_fn(work_text)
                    self.audit.log("output_produced", AuditLogger.hash_text(out_covered),
                                   meta={"ghost": False, "fallback": True})
                    if _cover is not None:
                        out, reform, cover_meta = self._cover_finish(
                            out_covered, work_text, _cover)
                        cover_meta.update({"fallback": True, "guard": guard_report})
                        return FantasmaResultV02(
                            output=out,
                            ghost_activated=True,
                            reformulated_input=reform,
                            gate_reason=decisione.reason,
                            ghost_commitment=impegno,
                            key_commitment=None,
                            audit_ok=self.audit.verify(),
                            memory_empty_after=len(self._live_secrets) == 0,
                            cache_empty_after=len(self._sealed) == 0,
                            used_same_ai=True,
                            hygiene=self.hygiene_report,
                            meta=cover_meta,
                        )
                    return FantasmaResultV02(
                        output=out_covered,
                        ghost_activated=True,
                        reformulated_input=testo,
                        gate_reason=decisione.reason,
                        ghost_commitment=impegno,
                        key_commitment=None,
                        audit_ok=self.audit.verify(),
                        memory_empty_after=len(self._live_secrets) == 0,
                        cache_empty_after=len(self._sealed) == 0,
                        used_same_ai=True,
                        hygiene=self.hygiene_report,
                        meta={"fallback": True, "guard": guard_report},
                    )
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

        # 4. riformula + output finale (mai cifre; con cover: solo placeholder)
        riformulato_covered = (
            f"{interpretation.strip()}\nRichiesta originale: {work_text.strip()}"
        )
        self.audit.log("reformulated", AuditLogger.hash_text(riformulato_covered))
        del interpretation
        out_covered = self.llm_fn(riformulato_covered)
        self.audit.log("output_produced", AuditLogger.hash_text(out_covered), meta={"ghost": True})

        # 5. amnesia totale: distruggi CHIAVE (shredding), svuota sealed
        # v0.04 catenaccio: wipe idempotente ma registrato + ricevuta in
        # hash-chain (uid_hash/nonce/ts/prev, NULLA derivato dal codice).
        already_gone = shredder.is_destroyed
        shredder.destroy()
        self._sealed.clear()
        self.audit.log("ghost_erased", AuditLogger.hash_text(uid + ":erased"))
        receipt, first_bolt = self.bolts.bolt(uid_hash)
        if already_gone:
            self.audit.log("bolt_rewipe", receipt.entry_hash,
                           meta={"uid_hash": uid_hash, "first": False})
        self.audit.log("bolted", receipt.entry_hash,
                       meta={"uid_hash": uid_hash, "n": receipt.n,
                             "first": first_bolt})

        # cancella residui locali
        del shredder
        del secret

        if _cover is not None:
            out, riformulato, cover_meta = self._cover_finish(
                out_covered, riformulato_covered, _cover)
            cover_meta.update({"uid_hash": uid_hash, "guard": guard_report,
                               "bolt": receipt.to_dict(), "bolt_first": first_bolt,
                               "bolts_chain_ok": self.bolts.verify_chain()})
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
                meta=cover_meta,
            )

        return FantasmaResultV02(
            output=out_covered,
            ghost_activated=True,
            reformulated_input=riformulato_covered,
            gate_reason=decisione.reason,
            ghost_commitment=impegno,
            key_commitment=key_comm,
            audit_ok=self.audit.verify(),
            memory_empty_after=len(self._live_secrets) == 0,
            cache_empty_after=len(self._sealed) == 0,
            used_same_ai=True,
            hygiene=self.hygiene_report,
            meta={"uid_hash": uid_hash, "guard": guard_report,
                  "bolt": receipt.to_dict(), "bolt_first": first_bolt,
                  "bolts_chain_ok": self.bolts.verify_chain()},
        )
