"""
ReformOnly control arm — v0.03 T1, v0.04 con guard + prompt rigido.
Stessa Call-1 di Ghost (stesso prompt rigido FANTASMA-INTERPRETA),
Call-2 dalla sola riformulazione, SENZA SecretBytes / CryptoShredder / wipe.
Isola extra-compute (2 chiamate) da sealed-code.
v0.04: codice derivato uniforme (rejection sampling, mai int/str intero),
validazione allowlist con 1 retry, fallback Direct contato a parte.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass, field
from typing import Callable

from .codec import INTERPRET_MARKER
from .reform_guard import ReformulationGuard, build_call1_prompt
from .secret import digest_to_canonical_19


def _hmac_digest(nonce: str, text: str, salt: bytes) -> bytes:
    return hmac.new(salt, f"{nonce}:{text}".encode("utf-8"), hashlib.sha256).digest()


def _digest_to_numeric_bytes(digest: bytes, n_digits: int = 19) -> bytes:
    # v0.04: uniforme via rejection sampling (sostituisce f"{b:03d}" biasato).
    # n_digits diverso da 19: tronca/estende dal canonico a 19.
    canon = digest_to_canonical_19(digest)
    out = bytes(canon[:n_digits]) if n_digits <= 19 else bytes(canon) + b"0" * (n_digits - 19)
    for i in range(len(canon)):
        canon[i] = 0x00
    return out


@dataclass
class ReformOnlyResult:
    output: str
    reformulated_input: str
    interpretation: str
    ghost_code: str
    meta: dict = field(default_factory=dict)
    fallback: bool = False
    guard_report: dict = field(default_factory=dict)


class ReformOnlyPipeline:
    """Call-1 identica a FantasmaPipelineV02, ma codice in chiaro (no Secret),
    nessun seal, nessun wipe verificato. Solo reformulate-then-answer."""

    def __init__(
        self,
        llm_fn: Callable[[str], str] | None = None,
        salt: bytes | None = None,
    ) -> None:
        self.llm_fn = llm_fn
        if self.llm_fn is None:
            from .pipeline_v02 import default_mock_llm_v02
            self.llm_fn = default_mock_llm_v02
        self.salt = salt or secrets.token_bytes(32)

    def process(self, user_input: str) -> ReformOnlyResult:
        testo = user_input or ""
        guard = ReformulationGuard()
        nonce = uuid.uuid4().hex
        digest = _hmac_digest(nonce, testo, self.salt)
        code_buf = digest_to_canonical_19(digest)
        del digest
        code = bytes(code_buf).decode("ascii")
        for i in range(len(code_buf)):
            code_buf[i] = 0x00
        del code_buf
        prompt = build_call1_prompt(code, testo, marker=INTERPRET_MARKER)
        interpretation = self.llm_fn(prompt)
        rep = guard.validate_with_report(interpretation, testo)
        if not rep["ok"]:
            interpretation = self.llm_fn(prompt)  # 1 retry, mai sporco a Call-2
            rep = guard.validate_with_report(interpretation, testo)
            if not rep["ok"]:
                out = self.llm_fn(testo)  # fallback Direct, contato a parte
                return ReformOnlyResult(
                    output=out,
                    reformulated_input=testo,
                    interpretation="",
                    ghost_code="",
                    meta={"nonce": nonce, "fallback_reason": rep.get("reason", "")},
                    fallback=True,
                    guard_report=rep,
                )
        interpretation = rep["clean"] or ""
        riformulato = f"{interpretation.strip()}\nRichiesta originale: {testo.strip()}"
        out = self.llm_fn(riformulato)
        return ReformOnlyResult(
            output=out,
            reformulated_input=riformulato,
            interpretation=interpretation,
            ghost_code="",
            meta={"nonce": nonce},
            fallback=False,
            guard_report=rep,
        )
