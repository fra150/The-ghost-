"""
Adapter DeepSeek-V4.1-Flash per Il Fantasma — decisione stessa-AI (5.1).

Modello canonico API: `deepseek-flash` (= DeepSeek-V4.1-Flash, live dal 10/09/2026).
Base URL: https://api.deepseek.com (formato OpenAI-compatibile).
Parametri del tuo snippet: reasoning_effort="high", thinking={"type":"enabled"}.

Uso:
    from fantasma.llm_deepseek import make_deepseek_llm
    from fantasma import FantasmaPipeline
    pipe = FantasmaPipeline(llm_fn=make_deepseek_llm())
    res = pipe.process("...")

La chiave NON va mai nel codice: solo env DEEPSEEK_API_KEY (file .env locale,
mai committato). Vedi .env.example.
"""

from __future__ import annotations

import os
from typing import Callable


DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-flash"  # = DeepSeek-V4.1-Flash
DEFAULT_REASONING_EFFORT = "high"


def load_env(dotenv_path: str | None = None) -> None:
    """Carica .env se python-dotenv e' disponibile (best-effort, mai obbligatorio)."""
    try:
        from dotenv import load_dotenv

        load_dotenv(dotenv_path or ".env")
    except ImportError:
        pass


def _normalize_model(name: str) -> str:
    """Mappa nomi display (es. DeepSeek-V4.1-Flash) all'id API canonico deepseek-flash."""
    n = (name or "").strip().lower().replace("_", "-").replace(" ", "-")
    # varianti display -> id canonico (docs: deepseek-flash = V4.1-Flash)
    if n in (
        "deepseek-v4.1-flash",
        "deepseek-v4-1-flash",
        "deepseek-v41-flash",
        "deepseek-flash",
        "deepseek-v4-flash",
        "deepseek-v4-flash-vision-exp",
    ):
        return "deepseek-flash"
    return (name or "").strip() or DEFAULT_MODEL


def get_config() -> dict:
    load_env()
    return {
        "api_key": os.environ.get("DEEPSEEK_API_KEY", "").strip(),
        "base_url": os.environ.get("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL).strip() or DEFAULT_BASE_URL,
        "model": _normalize_model(os.environ.get("DEEPSEEK_MODEL", DEFAULT_MODEL)),
        "reasoning_effort": os.environ.get("DEEPSEEK_REASONING_EFFORT", DEFAULT_REASONING_EFFORT).strip()
        or DEFAULT_REASONING_EFFORT,
        "thinking": os.environ.get("DEEPSEEK_THINKING", "enabled").strip() or "enabled",
        "system": os.environ.get(
            "DEEPSEEK_SYSTEM", "You are a helpful assistant"
        ).strip() or "You are a helpful assistant",
    }


def make_deepseek_llm(
    system: str | None = None,
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    reasoning_effort: str | None = None,
) -> Callable[[str], str]:
    """
    Ritorna llm_fn(prompt) -> testo, compatibile con FantasmaPipeline.
    La STESSA funzione serve sia per interpretare il codice fantasma (5.1)
    sia per generare l'output finale — stessa AI, due ruoli.
    """
    cfg = get_config()
    _key = (api_key or cfg["api_key"]).strip()
    _base = (base_url or cfg["base_url"]).strip()
    _model = _normalize_model(model or cfg["model"])
    _effort = (reasoning_effort or cfg["reasoning_effort"]).strip()
    _system = (system or cfg["system"]).strip()
    _thinking = cfg["thinking"]

    if not _key:
        raise RuntimeError(
            "Manca DEEPSEEK_API_KEY. Mettila nel file .env (vedi .env.example): "
            "DEEPSEEK_API_KEY=sk-... — mai nel codice, mai su git."
        )

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("Manca OpenAI SDK: esegui `pip install openai` (o -r requirements.txt).") from exc

    client = OpenAI(api_key=_key, base_url=_base)

    def llm_fn(prompt: str) -> str:
        testo = (prompt or "").strip()
        if not testo:
            return ""
        resp = client.chat.completions.create(
            model=_model,
            messages=[
                {"role": "system", "content": _system},
                {"role": "user", "content": testo},
            ],
            stream=False,
            reasoning_effort=_effort,
            extra_body={"thinking": {"type": _thinking}},
        )
        return (resp.choices[0].message.content or "").strip()

    # metadati utili per debug/audit (mai la chiave)
    llm_fn.__fantasma__ = {"base_url": _base, "model": _model, "reasoning_effort": _effort}  # type: ignore[attr-defined]
    return llm_fn


def ping() -> str:
    """Check rapido: 'Hello' al modello configurato. Ritorna la risposta."""
    llm = make_deepseek_llm()
    return llm("Hello")
