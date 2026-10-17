"""
DeepSeek traced wrapper — v0.03 T4.
Ritorna content come prima (compatibile llm_fn), ma salva anche
reasoning_content (thinking) per leakage test.
Uso:
  from fantasma.llm_deepseek_traced import make_deepseek_llm_traced
  llm, trace = make_deepseek_llm_traced()
  out = llm("...")  # content
  # trace = [{"prompt":..., "content":..., "thinking":...}, ...]
"""
from __future__ import annotations

from typing import Callable


def make_deepseek_llm_traced(
    system: str | None = None, **kwargs
) -> tuple[Callable[[str], str], list]:
    from .llm_deepseek import get_config, _normalize_model

    cfg = get_config()
    _key = (kwargs.get("api_key") or cfg["api_key"]).strip()
    _base = (kwargs.get("base_url") or cfg["base_url"]).strip()
    _model = _normalize_model(kwargs.get("model") or cfg["model"])
    _effort = (kwargs.get("reasoning_effort") or cfg["reasoning_effort"]).strip()
    _system = (system or cfg["system"]).strip()
    _thinking = cfg["thinking"]
    # v0.04 P0: sampling richiesto registrato per riga di trace.
    _temp = float(kwargs.get("temperature", cfg.get("temperature", 0.0)))
    _top_p = float(kwargs.get("top_p", cfg.get("top_p", 1.0)))
    _seed = kwargs.get("seed", cfg.get("seed"))
    requested = {"temperature": _temp, "top_p": _top_p, "seed": _seed,
                 "reasoning_effort": _effort, "thinking": _thinking}

    if not _key:
        raise RuntimeError("Manca DEEPSEEK_API_KEY nel .env")

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("Manca openai SDK") from exc

    client = OpenAI(api_key=_key, base_url=_base)
    trace: list = []

    def llm_fn(prompt: str) -> str:
        testo = (prompt or "").strip()
        if not testo:
            return ""
        create_kw: dict = dict(
            model=_model,
            messages=[
                {"role": "system", "content": _system},
                {"role": "user", "content": testo},
            ],
            stream=False,
            reasoning_effort=_effort,
            extra_body={"thinking": {"type": _thinking}},
            temperature=_temp,
            top_p=_top_p,
        )
        if _seed is not None:
            create_kw["seed"] = _seed
        resp = client.chat.completions.create(**create_kw)
        msg = resp.choices[0].message
        content = (msg.content or "").strip()
        thinking = getattr(msg, "reasoning_content", None)
        if thinking is None and hasattr(msg, "model_extra") and msg.model_extra:
            thinking = msg.model_extra.get("reasoning_content", "")
        thinking = (thinking or "").strip()
        trace.append({"prompt": testo[:4000], "content": content[:4000], "thinking": thinking[:8000],
                      "params_requested": dict(requested)})
        return content

    llm_fn.__fantasma_traced__ = True  # type: ignore[attr-defined]
    llm_fn.params = dict(requested)  # type: ignore[attr-defined]
    llm_fn.params["note"] = "richiesti, non garantiti su thinking"  # type: ignore[attr-defined]
    return llm_fn, trace
