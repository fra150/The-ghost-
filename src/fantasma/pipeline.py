"""
Pipeline 1->6 con decisioni 5.1 / 5.2 / 5.3 del dr. Bulla:

5.1 STESSA AI INTERPRETA: il codice numerico viene riconsegnato allo
    stesso llm_fn che lo ha generato, tramite prompt FANTASMA-INTERPRETA.
    Nessun decodificatore esterno. La riformulazione nasce da quella
    lettura interna, non da un parser di vettori.

5.2 CACHE OFFUSCATA: il raw vive solo in EphemeralMemory per il giro di
    interpretazione. Subito dopo viene sigillato in ObfuscatedCache in
    forma offuscata (shift cifre da salt). Il raw viene wipato.

5.3 AMNESIA DOPO OUTPUT: sputato l'output, non serve ricordare.
    Memoria effimera + cache offuscata vengono svuotate. Resta solo
    l'audit (hash, mai contenuti).

Flusso:
1. input -> 2. gate -> 3. genera fantasma (raw transient)
-> 4. stessa AI interpreta il codice -> 5. sigillo offuscato + wipe raw
-> 6. riformula da interpretazione -> 7. output finale
-> 8. amnesia totale + audit ghost_erased
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .audit import AuditLogger
from .codec import INTERPRET_MARKER, GhostThought, PrivateNumericCodec
from .gate import HeuristicGate
from .memory import EphemeralMemory, ObfuscatedCache


def default_mock_llm(prompt: str) -> str:
    """
    Stessa AI simulata nei due ruoli (decisione 5.1):
    - se il prompt e' FANTASMA-INTERPRETA: legge le proprie cifre e
      restituisce una direttiva di riformulazione (senza cifre);
    - altrimenti: genera l'output finale dalla versione riformulata.
    In produzione sostituire con la chiamata al modello reale.
    """
    s = (prompt or "").strip()
    if not s:
        return "Output finale: (input vuoto, niente da raffinare.)"

    if INTERPRET_MARKER in s:
        # la stessa AI rilegge le proprie cifre: deriva lo stile dalle cifre
        cifre = "".join(ch for ch in s if ch.isdigit())
        # prendi solo il blocco del codice (19 cifre v0.1): e' il piu' lungo
        # euristica mock onesta: somma cifre % 3 sceglie la direttiva
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


@dataclass
class FantasmaResult:
    output: str
    ghost_activated: bool
    reformulated_input: str
    gate_reason: str
    ghost_commitment: str | None  # hash del pensiero, mai il pensiero
    audit_ok: bool
    memory_empty_after: bool  # effimera vuota
    cache_empty_after: bool  # cache offuscata vuota (amnesia 5.3)
    used_same_ai: bool = False  # 5.1: interpretato dalla stessa AI
    meta: dict = field(default_factory=dict)


class FantasmaPipeline:
    def __init__(
        self,
        gate: HeuristicGate | None = None,
        codec: PrivateNumericCodec | None = None,
        memory: EphemeralMemory | None = None,
        cache: ObfuscatedCache | None = None,
        audit: AuditLogger | None = None,
        llm_fn: Callable[[str], str] | None = None,
    ) -> None:
        self.gate = gate or HeuristicGate()
        self.codec = codec or PrivateNumericCodec()
        self.memory = memory or EphemeralMemory()
        # la cache offuscata deriva dal salt = stato interno della stessa AI
        self.cache = cache or ObfuscatedCache(salt=self.codec.secret_salt)
        self.audit = audit or AuditLogger()
        self.llm_fn = llm_fn or default_mock_llm

    def _interpret_via_same_ai(self, original_input: str, ghost: GhostThought) -> str:
        """
        Decisione 5.1: riconsegna il codice alla STESSA AI.
        Il raw numerico esiste solo come argomento di questa chiamata.
        """
        prompt = self.codec.build_interpret_prompt(ghost, original_input)
        interpretation = self.llm_fn(prompt)
        return interpretation

    def process(self, user_input: str) -> FantasmaResult:
        testo = user_input or ""

        # 1. input
        self.audit.log("input_received", AuditLogger.hash_text(testo))

        # 2. gate
        decisione = self.gate.should_activate(testo)
        self.audit.log(
            "gate_decision",
            AuditLogger.hash_text(decisione.reason),
            meta={"active": decisione.active, "score": decisione.score},
        )

        # standby: nessun fantasma, chiamata diretta
        if not decisione.active:
            out = self.llm_fn(testo)
            self.audit.log("output_produced", AuditLogger.hash_text(out), meta={"ghost": False})
            return FantasmaResult(
                output=out,
                ghost_activated=False,
                reformulated_input=testo,
                gate_reason=decisione.reason,
                ghost_commitment=None,
                audit_ok=self.audit.verify(),
                memory_empty_after=len(self.memory) == 0,
                cache_empty_after=len(self.cache) == 0,
                used_same_ai=False,
            )

        # 3. generazione pensiero numerico (raw transient)
        ghost = self.codec.generate(testo)
        raw_code = ghost.numeric_code  # vive solo in questo scope
        uid = ghost.uid
        self.memory.put(ghost)
        impegno = ghost.commitment()
        self.audit.log("ghost_activated", impegno, meta={"uid_hash": AuditLogger.hash_text(uid)})

        # 4. STESSA AI interpreta il proprio codice (5.1)
        interpretation = self._interpret_via_same_ai(testo, ghost)
        self.audit.log("ghost_interpreted", AuditLogger.hash_text(interpretation))

        # 5. sigillo offuscato in cache + wipe raw (5.2)
        trace = self.cache.seal(ghost)
        self.audit.log("cached_obfuscated", AuditLogger.hash_text(trace.obfuscated_code))
        self.memory.forget(uid)
        # wipe riferimenti locali al raw
        try:
            ghost.numeric_code = "0" * len(ghost.numeric_code)
            ghost.vector = []
            raw_code = "0" * len(raw_code)
        finally:
            del ghost
            del raw_code

        # 6. riformulazione guidata dalla lettura della stessa AI (mai cifre)
        riformulato = f"{interpretation.strip()}\nRichiesta originale: {testo.strip()}"
        self.audit.log("reformulated", AuditLogger.hash_text(riformulato))

        # 7. output finale
        out = self.llm_fn(riformulato)
        self.audit.log("output_produced", AuditLogger.hash_text(out), meta={"ghost": True})

        # 8. amnesia di progetto (5.3): sputato l'output, non serve ricordare
        self.cache.clear()
        self.memory.selective_reset()
        self.audit.log("ghost_erased", AuditLogger.hash_text(uid + ":erased"))

        return FantasmaResult(
            output=out,
            ghost_activated=True,
            reformulated_input=riformulato,
            gate_reason=decisione.reason,
            ghost_commitment=impegno,
            audit_ok=self.audit.verify(),
            memory_empty_after=len(self.memory) == 0,
            cache_empty_after=len(self.cache) == 0,
            used_same_ai=True,
            meta={"interpretation_hash": AuditLogger.hash_text(interpretation)},
        )
