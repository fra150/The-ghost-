"""
Il Fantasma v0.03 — llm_ollama.py
Adapter per modelli open-weights in locale via Ollama (http://localhost:11434).

Perche': con modello locale nessun prompt lascia la macchina fisica:
L3 passa da "dichiarato" (provider remoto) a operativo/misurabile.
Niente chiavi, niente header di auth: solo HTTP su loopback.

Uso:
    llm = make_ollama_llm(model="gemma4")   # callable str->str come gli altri adapter
    pipe = FantasmaPipelineV02(llm_fn=llm)

Ogni chiamata aggiorna `llm.stats` (eval/prompt_eval/ms, quando il server
li riporta) per le metriche di costo della v0.03. Mai eccezioni silenziose:
al secondo fallimento consecutivo l'errore propaga e l'harness lo registra.
"""

from __future__ import annotations

import json
import urllib.request
from typing import Callable

DEFAULT_MODEL = "gemma4"
DEFAULT_HOST = "http://localhost:11434"
DEFAULT_TIMEOUT = 600.0
MAX_ATTEMPTS = 2


def _raw_generate(host: str, model: str, prompt: str, options: dict | None,
                  think: bool | None, timeout: float) -> tuple[str, dict]:
    """POST /api/generate via stdlib (supporta think anche con client datati)."""
    payload: dict = {"model": model, "prompt": prompt, "stream": False}
    if options:
        payload["options"] = options
    if think is not None:
        payload["think"] = think
    req = urllib.request.Request(
        host.rstrip("/") + "/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as fh:
        r = json.loads(fh.read().decode("utf-8"))
    stats = {"eval": r.get("eval_count"), "prompt_eval": r.get("prompt_eval_count"),
             "ms": (r.get("total_duration") or 0) // 10**6}
    return r.get("response", "") or "", stats


def make_ollama_llm(
    model: str = DEFAULT_MODEL,
    temperature: float | None = 0.0,
    num_predict: int | None = None,
    think: bool | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    host: str = DEFAULT_HOST,
    client=None,
    seed: int | None = 20261010,
    top_k: int | None = 1,
) -> Callable[[str], str]:
    """Ritorna llm_fn(prompt)->str. `client` iniettabile per i test (no rete).

    v0.04 P0 determinismo: default temperature=0.0, top_k=1, seed=20261010.
    Sono parametri RICHIESTI al server Ollama, registrati in llm_fn.params;
    su thinking restano non-determinismi residui -> servono >=3 ripetizioni.
    think=False disabilita il thinking server-side (molto piu' veloce su CPU;
    da dichiarare nel disegno: vale uguale per tutti i bracci).
    """
    if client is None:
        import ollama

        try:
            client = ollama.Client(timeout=timeout)
        except TypeError:  # client datati senza timeout
            client = ollama.Client()
    options: dict = {}
    if temperature is not None:
        options["temperature"] = temperature
    if num_predict is not None:
        options["num_predict"] = num_predict
    if top_k is not None:
        options["top_k"] = top_k
    if seed is not None:
        options["seed"] = seed

    def llm_fn(prompt: str) -> str:
        last_exc: Exception | None = None
        for _ in range(MAX_ATTEMPTS):
            try:
                if think is not None:
                    out, st = _raw_generate(host, model, prompt, options or None, think, timeout)
                    llm_fn.stats = st  # noqa: B023
                    return out
                kw: dict = {"model": model, "prompt": prompt, "options": options or None}
                r = client.generate(**kw)
                resp = r.get("response", "") if isinstance(r, dict) else getattr(r, "response", "")
                get = (lambda k: r.get(k)) if isinstance(r, dict) else (lambda k: getattr(r, k, None))
                llm_fn.stats = {  # noqa: B023
                    "eval": get("eval_count"),
                    "prompt_eval": get("prompt_eval_count"),
                    "ms": (get("total_duration") or 0) // 10**6,
                }
                return resp or ""
            except Exception as exc:  # noqa: BLE001 — ritenta una volta, poi propaga
                last_exc = exc
        raise last_exc  # type: ignore[misc]

    llm_fn.stats = {}  # type: ignore[attr-defined]
    llm_fn.model = model  # type: ignore[attr-defined]
    llm_fn.params = {"temperature": temperature, "top_k": top_k, "seed": seed,  # type: ignore[attr-defined]
                     "num_predict": num_predict, "think": think,
                     "note": "richiesti, non garantiti su thinking"}
    return llm_fn
