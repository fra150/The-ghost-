"""
Il Fantasma v0.04 — arms.py (P0 scientifico: bracci di ablazione).

Problema v0.03: Fantasma e ReformOnly eseguono le STESSE due chiamate;
il sigillo non puo' causalmente toccare la risposta -> H0 vera per
costruzione, non per misura. Questi bracci separano contenuto vs computo:

- reformonly_v04: Call-1 con codice derivato dalla domanda + Call-2 dalla
  sola riformulazione (controllo a pari computo, con guard + prompt rigido).
- clear: come reformonly, ma Call-2 riceve anche il codice IN CHIARO.
  Se clear == fantasma, nascondere e' gratis; se clear > fantasma,
  nascondere costa accuratezza (misura causale del blinding).
- random: Call-1 con codice CASUALE scollegato dalla domanda (CSPRNG con
  rejection sampling, mai int/str dell'intero codice), Call-2 dalla sola
  riformulazione. Se random == fantasma, conta solo l'extra-compute,
  non il contenuto del codice.

Tutti i bracci usano: stesso prompt rigido Call-1, stesso guard allowlist,
stesso retry (max 1 retry) + fallback Direct dichiarato e contato a parte.
"""

from __future__ import annotations

import hashlib
import hmac
import time

from .reform_guard import ReformulationGuard, build_call1_prompt
from .secret import digest_to_canonical_19, random_canonical_19

FORMAT_TAIL = "Rispondi con il numero finale nel formato: #### <numero>"


def derived_code(question: str, salt: bytes) -> bytearray:
    """Codice deterministico legato all'input, uniforme via rejection sampling.

    Sostituisce il vecchio `f"{b:03d}"` troncato (biasato). Nessun int/str
    dell'intero codice: HMAC -> digest -> cifre ASCII dirette nel bytearray.
    """
    msg = f"{question or ''}".encode("utf-8")
    digest = hmac.new(bytes(salt), msg, hashlib.sha256).digest()
    out = digest_to_canonical_19(digest)
    del digest
    return out


def _call1_with_guard(llm_fn, code_buf: bytearray, question: str,
                      guard: ReformulationGuard, max_retries: int = 1) -> dict:
    """Esegue Call-1 con retry su leakage. Ritorna {interpretation, guard_report, retries, leaked}."""
    # Display transiente per il prompt (str inevitabile verso LLM: origine
    # dichiarata delle copie L2). Non conservato oltre la chiamata.
    code_display = bytes(code_buf).decode("ascii")
    prompt = build_call1_prompt(code_display, question)
    code_display = "0" * len(code_display)
    del code_display
    last_report: dict = {}
    for attempt in range(max_retries + 1):
        interp = llm_fn(prompt)
        rep = guard.validate_with_report(interp, question)
        last_report = rep
        if rep["ok"]:
            return {"interpretation": rep["clean"], "guard_report": rep,
                    "retries": attempt, "leaked": attempt > 0}
        if attempt < max_retries:
            continue
        return {"interpretation": None, "guard_report": rep,
                "retries": attempt, "leaked": True}
    return {"interpretation": None, "guard_report": last_report,
            "retries": max_retries, "leaked": True}


def _direct_fallback(llm_fn, question: str) -> str:
    return llm_fn(f"{question}\n{FORMAT_TAIL}")


def run_arm_reformonly_v04(llm_fn, question: str, salt: bytes,
                           guard: ReformulationGuard | None = None,
                           max_retries: int = 1) -> dict:
    t0 = time.time()
    guard = guard or ReformulationGuard()
    code = derived_code(question, salt)
    r1 = _call1_with_guard(llm_fn, code, question, guard, max_retries)
    for i in range(len(code)):
        code[i] = 0x00
    del code
    if r1["interpretation"] is None:
        out = _direct_fallback(llm_fn, question)
        return {"output": out, "interpretation": "", "reformulated": question,
                "guard": r1["guard_report"], "fallback": True,
                "code_source": "derived", "seconds": time.time() - t0}
    reform = f"{r1['interpretation'].strip()}\nRichiesta originale: {question.strip()}"
    out = llm_fn(f"{reform}\n{FORMAT_TAIL}")
    return {"output": out, "interpretation": r1["interpretation"], "reformulated": reform,
            "guard": r1["guard_report"], "fallback": False,
            "code_source": "derived", "seconds": time.time() - t0}


def run_arm_clear_v04(llm_fn, question: str, salt: bytes,
                      guard: ReformulationGuard | None = None,
                      max_retries: int = 1) -> dict:
    """Pensiero-in-chiaro: Call-2 vede codice + riformulazione."""
    t0 = time.time()
    guard = guard or ReformulationGuard()
    code = derived_code(question, salt)
    code_display = bytes(code).decode("ascii")
    r1 = _call1_with_guard(llm_fn, code, question, guard, max_retries)
    if r1["interpretation"] is None:
        for i in range(len(code)):
            code[i] = 0x00
        del code
        out = _direct_fallback(llm_fn, question)
        return {"output": out, "interpretation": "", "reformulated": question,
                "guard": r1["guard_report"], "fallback": True,
                "code_source": "derived-clear", "seconds": time.time() - t0}
    reform = (f"Codice (in chiaro, controllo): {code_display}\n"
              f"{r1['interpretation'].strip()}\nRichiesta originale: {question.strip()}")
    for i in range(len(code)):
        code[i] = 0x00
    del code
    code_display = "0" * len(code_display)
    del code_display
    out = llm_fn(f"{reform}\n{FORMAT_TAIL}")
    return {"output": out, "interpretation": r1["interpretation"], "reformulated": reform,
            "guard": r1["guard_report"], "fallback": False,
            "code_source": "derived-clear", "seconds": time.time() - t0}


def run_arm_random_v04(llm_fn, question: str, salt: bytes | None = None,
                       guard: ReformulationGuard | None = None,
                       max_retries: int = 1) -> dict:
    """Cifre-casuali: codice CSPRNG scollegato dalla domanda."""
    t0 = time.time()
    guard = guard or ReformulationGuard()
    code = random_canonical_19()
    r1 = _call1_with_guard(llm_fn, code, question, guard, max_retries)
    for i in range(len(code)):
        code[i] = 0x00
    del code
    if r1["interpretation"] is None:
        out = _direct_fallback(llm_fn, question)
        return {"output": out, "interpretation": "", "reformulated": question,
                "guard": r1["guard_report"], "fallback": True,
                "code_source": "random", "seconds": time.time() - t0}
    reform = f"{r1['interpretation'].strip()}\nRichiesta originale: {question.strip()}"
    out = llm_fn(f"{reform}\n{FORMAT_TAIL}")
    return {"output": out, "interpretation": r1["interpretation"], "reformulated": reform,
            "guard": r1["guard_report"], "fallback": False,
            "code_source": "random", "seconds": time.time() - t0}
