"""
Benchmark GSM8K per il Fantasma — pilota verso 50.

Perche' GSM8K: il piu' popolare per il ragionamento con risposte verificabili
senza giudice (numero esatto dopo ####). Il Fantasma incornicia bene e qui
l'incorniciatura si misura: accuratezza exact-match a parita' di modello.

Bracci (stesso llm_fn, stesso formato finale):
  A direct  : domanda + istruzione formato, una chiamata.
  B hidden  : 'ragiona in privato senza mostrarlo, poi solo #### numero'.
  C fantasma: pipeline v0.02 (ghost -> stessa-AI -> seal -> output -> amnesia).

Istruzione formato accodata a tutti: 'Rispondi con il numero finale nel formato: #### <numero>'.
Score: regex su ####, normalizza virgole, confronto numerico con gold dopo ####.
Per ogni item: gold, pred, corretto, ghost_activated, audit_ok, mem/cache vuote, tempi.
Output: JSONL per-item + summary.json in outputs/benchmark/.
"""

from __future__ import annotations

import json
import random
import re
import time
from pathlib import Path

FORMAT_LINE = "Rispondi con il numero finale nel formato: #### <numero>"

GOLD_RE = re.compile(r"####\s*(-?[\d,]+(?:\.\d+)?)")
PRED_RE = re.compile(r"####\s*(-?[\d,]+(?:\.\d+)?)")


def gold_number(answer: str) -> str:
    m = GOLD_RE.search(answer or "")
    if not m:
        raise ValueError("gold senza ####")
    return m.group(1).replace(",", "")


def pred_number(output: str) -> str | None:
    ms = PRED_RE.findall(output or "")
    if not ms:
        return None
    return ms[-1].replace(",", "")


def same_number(a: str, b: str) -> bool:
    try:
        return abs(float(a) - float(b)) < 1e-6
    except Exception:
        return a.strip() == b.strip()


def load_sample(n: int, seed: int = 20261010):
    from datasets import load_dataset

    ds = load_dataset("openai/gsm8k", "main", split="test")
    idx = list(range(len(ds)))
    rnd = random.Random(seed)
    rnd.shuffle(idx)
    return [ds[i] for i in idx[:n]]


def run_arm_direct(llm_fn, question: str) -> dict:
    t0 = time.time()
    out = llm_fn(f"{question}\n{FORMAT_LINE}")
    return {"output": out, "seconds": time.time() - t0}


def run_arm_hidden(llm_fn, question: str) -> dict:
    t0 = time.time()
    out = llm_fn(
        f"{question}\nRagiona passo passo nel tuo pensiero privato senza mostrarlo. "
        f"Mostra solo il risultato. {FORMAT_LINE}"
    )
    return {"output": out, "seconds": time.time() - t0}


def run_arm_fantasma(pipe, question: str) -> dict:
    t0 = time.time()
    res = pipe.process(f"{question}\n{FORMAT_LINE}")
    return {
        "output": res.output,
        "seconds": time.time() - t0,
        "ghost_activated": res.ghost_activated,
        "audit_ok": res.audit_ok,
        "memory_empty_after": res.memory_empty_after,
        "cache_empty_after": res.cache_empty_after,
    }


def run_benchmark(n: int, seed: int, arms: tuple = ("direct", "hidden", "fantasma"),
                  outdir: str = "outputs/benchmark", tag: str = "pilot") -> dict:
    from .llm_deepseek import make_deepseek_llm
    from .pipeline_v02 import FantasmaPipelineV02

    llm = make_deepseek_llm()
    sample = load_sample(n, seed)
    out_path = Path(outdir)
    out_path.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    score = {a: 0 for a in arms}
    counted = {a: 0 for a in arms}
    for i, item in enumerate(sample):
        q = item["question"]
        try:
            gold = gold_number(item["answer"])
        except ValueError:
            continue
        row: dict = {"i": i, "question": q[:200], "gold": gold, "arms": {}}
        if "direct" in arms:
            r = run_arm_direct(llm, q)
            p = pred_number(r["output"])
            ok = p is not None and same_number(p, gold)
            row["arms"]["direct"] = {"pred": p, "ok": ok, "seconds": round(r["seconds"], 1)}
            score["direct"] += ok
            counted["direct"] += 1
        if "hidden" in arms:
            r = run_arm_hidden(llm, q)
            p = pred_number(r["output"])
            ok = p is not None and same_number(p, gold)
            row["arms"]["hidden"] = {"pred": p, "ok": ok, "seconds": round(r["seconds"], 1)}
            score["hidden"] += ok
            counted["hidden"] += 1
        if "fantasma" in arms:
            pipe = FantasmaPipelineV02(llm_fn=llm)
            r = run_arm_fantasma(pipe, q)
            p = pred_number(r["output"])
            ok = p is not None and same_number(p, gold)
            row["arms"]["fantasma"] = {
                "pred": p, "ok": ok, "seconds": round(r["seconds"], 1),
                "ghost": r["ghost_activated"], "audit_ok": r["audit_ok"],
                "mem_empty": r["memory_empty_after"], "cache_empty": r["cache_empty_after"],
            }
            score["fantasma"] += ok
            counted["fantasma"] += 1
        rows.append(row)
        with open(out_path / f"{tag}.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    summary = {
        "tag": tag, "n": len(rows), "seed": seed, "arms": list(arms),
        "accuracy": {a: round(score[a] / max(1, counted[a]), 3) for a in arms},
        "correct": score, "counted": counted,
    }
    with open(out_path / f"{tag}_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    return summary
