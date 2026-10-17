"""
Il Fantasma v0.03 — bench_gsm8k_v03.py
Harness locale: stessi 3 bracci della v0.02 (direct/hidden/fantasma),
stesso scoring su ####, ma llm_fn iniettabile (locale via llm_ollama)
e campionamento pre-registrato random|stratified.

Disegno pre-registrato (v0.03):
- random: primi n dallo shuffle con seed (confronto pulito).
- stratified: sweep direct sull'intero pool (shuffle+seed), si prendono i
  primi n fallimenti del direct ("hard cases": massimizza la potenza per
  rilevare se il ragionamento nascosto aggiunge valore). Se i fallimenti
  sono < n, si riempie con successi casuali (riportato in summary come
  `fill_random`). Lo sweep direct e' riusato come braccio direct in fase 2
  (niente doppie chiamate) ed e' resumabile da {tag}_direct_sweep.jsonl.
- Statistica: McNemar appaiato (chi2 con correzione di continuita'; esatto
  binomiale se b+c<25) fantasma-vs-direct e fantasma-vs-hidden, alfa 0.05,
  + bootstrap (10k) sulla differenza di accuratezza con IC 95%.
- Metriche: accuratezza, latenza media/p95 per braccio, token totali
  (eval/prompt_eval quando l'adapter li espone).

Uso:
    python -m fantasma.bench_gsm8k_v03 --model gemma4 --n 20 --mode random --tag pilot20_local
    python -m fantasma.bench_gsm8k_v03 --model gemma4 --n 500 --mode stratified --tag gsm8k_500_local
"""

from __future__ import annotations

import argparse
import json
import math
import random
import time
from pathlib import Path

from .bench_gsm8k import (
    FORMAT_LINE,
    gold_number,
    load_sample,
    pred_number,
    run_arm_direct,
    run_arm_fantasma,
    run_arm_hidden,
    same_number,
)

ALPHA = 0.05
BOOT_ITERS = 10_000


# -- statistica (stdlib) ----------------------------------------------------

def mcnemar(b: int, c: int) -> dict:
    """b = fantasma ok & altro ko; c = altro ok & fantasma ko."""
    n = b + c
    if n == 0:
        return {"b": b, "c": c, "chi2": 0.0, "p": 1.0, "method": "no-discordant"}
    if n < 25:  # esatto binomiale two-sided
        p = sum(math.comb(n, k) for k in range(n + 1) if abs(k - n / 2) >= abs(b - n / 2))
        p = min(1.0, p / 2**n)
        return {"b": b, "c": c, "chi2": None, "p": round(p, 6), "method": "exact-binomial"}
    chi2 = (abs(b - c) - 1) ** 2 / n
    p = math.erfc(math.sqrt(chi2 / 2))  # chi2 a 1 gdl
    return {"b": b, "c": c, "chi2": round(chi2, 4), "p": round(p, 6), "method": "chi2-cc"}


def bootstrap_diff(a_ok: list[bool], b_ok: list[bool], iters: int = BOOT_ITERS, seed: int = 0) -> dict:
    """Differenza di accuratezza (a-b) con IC 95% percentile. a,b appaiati."""
    n = len(a_ok)
    rnd = random.Random(seed)
    base = sum(a_ok) / n - sum(b_ok) / n
    diffs = []
    for _ in range(iters):
        sa = sb = 0
        for _ in range(n):
            i = rnd.randrange(n)
            sa += a_ok[i]
            sb += b_ok[i]
        diffs.append(sa / n - sb / n)
    diffs.sort()
    lo = diffs[int(0.025 * iters)]
    hi = diffs[int(0.975 * iters)]
    return {"diff": round(base, 4), "ci95": [round(lo, 4), round(hi, 4)], "iters": iters}


def _p95(xs: list[float]) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    return s[min(len(s) - 1, int(0.95 * len(s)))]


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


# -- llm metered ------------------------------------------------------------

def wrap_metered(llm_fn):
    """Avvolge llm_fn accumulando stats per chiamata in log (non tocca l'interfaccia)."""
    log: list[dict] = []

    def fn(prompt: str) -> str:
        before = len(log)
        out = llm_fn(prompt)
        st = dict(getattr(llm_fn, "stats", {}) or {})
        log.append(st)
        assert len(log) == before + 1
        return out

    # v0.04: propaga i parametri di sampling richiesti per il reporting.
    try:
        fn.params = dict(getattr(llm_fn, "params", {}) or {})  # type: ignore[attr-defined]
    except Exception:
        pass
    return fn, log


def _tok(log: list[dict], key: str) -> int:
    return sum((e.get(key) or 0) for e in log if isinstance(e.get(key), int))


# -- campionamento ----------------------------------------------------------

def _sweep_path(outdir: Path, tag: str) -> Path:
    return outdir / f"{tag}_direct_sweep.jsonl"


def load_sweep(outdir: Path, tag: str) -> dict[int, dict]:
    """Risultati direct per indice pool (per resume)."""
    got: dict[int, dict] = {}
    p = _sweep_path(outdir, tag)
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                got[r["pool_i"]] = r
    return got


def direct_sweep(pool: list, llm_fn, seed: int, outdir: Path, tag: str,
                 order: list[int], cap: int | None = None) -> dict[int, dict]:
    """Fase 1 (stratified): direct su tutto il pool, append incrementale, resumabile."""
    outdir.mkdir(parents=True, exist_ok=True)
    got = load_sweep(outdir, tag)
    metered, log = wrap_metered(llm_fn)
    scan = order if cap is None else order[:cap]
    with open(_sweep_path(outdir, tag), "a", encoding="utf-8") as f:
        for pi in scan:
            if pi in got:
                continue
            item = pool[pi]
            try:
                gold = gold_number(item["answer"])
            except ValueError:
                continue
            t0 = time.time()
            try:
                out = metered(f"{item['question']}\n{FORMAT_LINE}")
                p = pred_number(out)
                ok = p is not None and same_number(p, gold)
                err = None
            except Exception as exc:  # noqa: BLE001 — registrato, non fatale
                p, ok, err = None, False, f"{type(exc).__name__}"
            n0 = len(log)
            row = {"pool_i": pi, "gold": gold, "pred": p, "ok": ok, "error": err,
                   "seconds": round(time.time() - t0, 1),
                   "eval": _tok(log[n0:], "eval"), "prompt_eval": _tok(log[n0:], "prompt_eval")}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            got[pi] = row
    return got


def select_sample(pool: list, n: int, mode: str, seed: int, llm_fn,
                  outdir: Path, tag: str) -> tuple[list[int], dict]:
    """Ritorna (indici pool selezionati, info disegno)."""
    rnd = random.Random(seed)
    order = list(range(len(pool)))
    rnd.shuffle(order)
    if mode == "random":
        return order[:n], {"mode": "random", "seed": seed}
    got = direct_sweep(pool, llm_fn, seed, outdir, tag, order)
    fails = [pi for pi in order if pi in got and not got[pi]["ok"]]
    take = fails[:n]
    fill = 0
    if len(take) < n:  # fallimenti insufficienti: riempi con successi (dichiarato)
        succ = [pi for pi in order if pi in got and got[pi]["ok"] and pi not in take]
        take += succ[: n - len(take)]
        fill = len(take) - len(fails[:n])
    info = {"mode": "stratified", "seed": seed, "pool": len(pool),
            "swept": len(got), "failures_found": len(fails), "fill_random": fill}
    return take, info


# -- run --------------------------------------------------------------------

V04_ARMS = ("direct", "hidden", "fantasma", "reformonly", "clear", "random")


def _llm_params_of(llm_fn) -> dict:
    try:
        return dict(getattr(llm_fn, "params", {}) or {})
    except Exception:
        return {}


def run_benchmark_v03(n: int, seed: int, mode: str, llm_fn, model_name: str,
                      arms: tuple = ("direct", "hidden", "fantasma"),
                      outdir: str = "outputs/benchmark", tag: str = "v03",
                      pool_n: int | None = None, repeats: int = 1) -> dict:
    """Harness v0.03 + estensioni v0.04 (retrocompatibile).

    v0.04 aggiunge, senza rompere le chiamate esistenti:
    - bracci `reformonly` (controllo 2-call con guard), `clear`
      (pensiero-in-chiaro: Call-2 vede il codice), `random` (cifre-casuali
      scollegate dalla domanda) — vedi arms.py;
    - `repeats` >= 1: ogni braccio viene eseguito `repeats` volte per item;
      con repeats > 1 si riportano stabilita' (flip rate) e accuratezza media
      su tutte le chiamate (temperature=0 NON basta su thinking);
    - reporting guard a 3 colonne (pulite/fallback/totale) + tasso di intervento;
    - blocco determinismo con parametri richiesti vs nota onesta.
    Default invariato: repeats=1, arms a 3 -> output v0.03 identico + metadati.
    """
    from .pipeline_v02 import FantasmaPipelineV02

    for _a in arms:
        if _a not in V04_ARMS:
            raise ValueError(f"braccio sconosciuto: {_a} (attesi {V04_ARMS})")
    repeats = max(1, int(repeats))
    import hashlib as _hl
    v04_salt = _hl.sha256(f"fantasma-v04-{seed}".encode()).digest()
    llm_requested = _llm_params_of(llm_fn)

    out_path = Path(outdir)
    out_path.mkdir(parents=True, exist_ok=True)
    pool = load_sample(pool_n or n if mode == "random" else (pool_n or 1319), seed)
    if mode == "random":
        pool = pool[:max(n, 1)]
    sel, info = select_sample(pool, n, mode, seed, llm_fn, out_path, tag)

    metered, log = wrap_metered(llm_fn)
    rows: list[dict] = []
    score = {a: 0 for a in arms}
    lat: dict[str, list[float]] = {a: [] for a in arms}
    toks: dict[str, dict[str, int]] = {a: {"eval": 0, "prompt_eval": 0} for a in arms}
    ok_lists: dict[str, list[bool]] = {a: [] for a in arms}
    # v0.04 reporting guard: interventi + accuratezza a 3 colonne.
    guard_fallbacks = {a: 0 for a in arms}
    guard_clean_ok = {a: 0 for a in arms}
    guard_clean_n = {a: 0 for a in arms}
    guard_fb_ok = {a: 0 for a in arms}
    guard_fb_n = {a: 0 for a in arms}
    # stabilita' su repeats: item con esiti non unanimi tra ripetizioni.
    flips = {a: 0 for a in arms}
    swept = load_sweep(out_path, tag) if mode == "stratified" else {}

    def _run_direct_once(question: str):
        m0 = len(log)
        t0 = time.time()
        try:
            out = metered(f"{question}\n{FORMAT_LINE}")
            err = None
        except Exception as exc:  # noqa: BLE001
            out, err = "", f"{type(exc).__name__}"
        sec = round(time.time() - t0, 1)
        ev, pe = _tok(log[m0:], "eval"), _tok(log[m0:], "prompt_eval")
        return out, err, sec, ev, pe

    def _run_hidden_once(question: str):
        m0 = len(log)
        t0 = time.time()
        try:
            r = run_arm_hidden(metered, question)
            out, err = r["output"], None
            sec = round(r.get("seconds", time.time() - t0), 1)
        except Exception as exc:  # noqa: BLE001
            out, err, sec = "", f"{type(exc).__name__}", round(time.time() - t0, 1)
        ev, pe = _tok(log[m0:], "eval"), _tok(log[m0:], "prompt_eval")
        return out, err, sec, ev, pe

    def _run_fantasma_once(question: str):
        m0 = len(log)
        t0 = time.time()
        try:
            pipe = FantasmaPipelineV02(llm_fn=metered)
            res = pipe.process(f"{question}\n{FORMAT_LINE}")
            out = res.output
            err = None
            sec = round(time.time() - t0, 1)
            meta = dict(getattr(res, "meta", {}) or {})
            extra = {"ghost": res.ghost_activated, "audit_ok": res.audit_ok,
                     "mem_empty": res.memory_empty_after,
                     "cache_empty": res.cache_empty_after,
                     "fallback": bool(meta.get("fallback", False)),
                     "guard_ok": None if not meta.get("guard") else bool(meta["guard"].get("ok", True))}
        except Exception as exc:  # noqa: BLE001
            out, err, sec = "", f"{type(exc).__name__}", round(time.time() - t0, 1)
            extra = {"fallback": False, "guard_ok": None}
        ev, pe = _tok(log[m0:], "eval"), _tok(log[m0:], "prompt_eval")
        return out, err, sec, ev, pe, extra

    def _run_ablation_once(kind: str, question: str):
        from .arms import run_arm_clear_v04, run_arm_random_v04, run_arm_reformonly_v04
        m0 = len(log)
        fn = {"reformonly": run_arm_reformonly_v04, "clear": run_arm_clear_v04,
              "random": run_arm_random_v04}[kind]
        try:
            # arms.py si aspetta la domanda pura; il formato #### e' aggiunto dentro.
            r = fn(metered, question, v04_salt)
            out = r["output"]
            # seconda passata di scoring sul formato: l'output deve contenere ####.
            err = None
            sec = round(r.get("seconds", 0.0), 1)
            extra = {"fallback": bool(r.get("fallback", False)),
                     "guard_ok": None if not r.get("guard") else bool(r["guard"].get("ok", True)),
                     "code_source": r.get("code_source", kind)}
        except Exception as exc:  # noqa: BLE001
            out, err, sec = "", f"{type(exc).__name__}", 0.0
            extra = {"fallback": False, "guard_ok": None, "code_source": kind}
        ev, pe = _tok(log[m0:], "eval"), _tok(log[m0:], "prompt_eval")
        return out, err, sec, ev, pe, extra

    with open(out_path / f"{tag}.jsonl", "a", encoding="utf-8") as f:
        for k, pi in enumerate(sel):
            item = pool[pi]
            gold = gold_number(item["answer"])
            row: dict = {"k": k, "pool_i": pi, "gold": gold, "arms": {}}
            if "direct" in arms:
                if pi in swept and repeats == 1:  # riuso fase 1, niente ricall
                    s = swept[pi]
                    ok, sec, ev, pe = s["ok"], s["seconds"], s["eval"], s["prompt_eval"]
                    row["arms"]["direct"] = {"pred": s["pred"], "ok": ok, "seconds": sec,
                                             "eval": ev, "prompt_eval": pe,
                                             "error": s.get("error"), "reused_phase1": True}
                    oks, preds = [ok], [s["pred"]]
                else:
                    oks, preds, secs, evs, pes, errs = [], [], [], [], [], []
                    for _r in range(repeats):
                        out, err, sec, ev, pe = _run_direct_once(item["question"])
                        pred = pred_number(out)
                        ok = pred is not None and same_number(pred, gold)
                        oks.append(ok)
                        preds.append(pred)
                        secs.append(sec)
                        evs.append(ev)
                        pes.append(pe)
                        errs.append(err)
                    ok = oks[0] if repeats == 1 else (sum(oks) / len(oks) >= 0.5)
                    sec = round(sum(secs) / len(secs), 1)
                    ev, pe = sum(evs), sum(pes)
                    row["arms"]["direct"] = {"pred": preds[0], "ok": ok, "seconds": sec,
                                             "eval": ev, "prompt_eval": pe, "error": errs[0],
                                             "repeats": repeats, "oks": oks, "preds": preds}
                    if repeats > 1 and not (all(oks) or not any(oks)):
                        flips["direct"] += 1
                score["direct"] += ok
                lat["direct"].append(sec)
                toks["direct"]["eval"] += ev
                toks["direct"]["prompt_eval"] += pe
                ok_lists["direct"].append(ok)
            if "hidden" in arms:
                oks, preds, secs, evs, pes, errs = [], [], [], [], [], []
                for _r in range(repeats):
                    out, err, sec, ev, pe = _run_hidden_once(item["question"])
                    pred = pred_number(out)
                    ok = pred is not None and same_number(pred, gold)
                    oks.append(ok)
                    preds.append(pred)
                    secs.append(sec)
                    evs.append(ev)
                    pes.append(pe)
                    errs.append(err)
                ok = oks[0] if repeats == 1 else (sum(oks) / len(oks) >= 0.5)
                sec = round(sum(secs) / len(secs), 1)
                ev, pe = sum(evs), sum(pes)
                row["arms"]["hidden"] = {"pred": preds[0], "ok": ok, "seconds": sec,
                                         "eval": ev, "prompt_eval": pe, "error": errs[0],
                                         "repeats": repeats, "oks": oks, "preds": preds}
                if repeats > 1 and not (all(oks) or not any(oks)):
                    flips["hidden"] += 1
                score["hidden"] += ok
                lat["hidden"].append(sec)
                toks["hidden"]["eval"] += ev
                toks["hidden"]["prompt_eval"] += pe
                ok_lists["hidden"].append(ok)
            if "fantasma" in arms:
                oks, preds, secs, evs, pes, errs, fbs = [], [], [], [], [], [], []
                last_extra: dict = {}
                for _r in range(repeats):
                    out, err, sec, ev, pe, extra = _run_fantasma_once(item["question"])
                    pred = pred_number(out)
                    ok = pred is not None and same_number(pred, gold)
                    oks.append(ok)
                    preds.append(pred)
                    secs.append(sec)
                    evs.append(ev)
                    pes.append(pe)
                    errs.append(err)
                    fbs.append(bool(extra.get("fallback", False)))
                    last_extra = extra
                ok = oks[0] if repeats == 1 else (sum(oks) / len(oks) >= 0.5)
                sec = round(sum(secs) / len(secs), 1)
                ev, pe = sum(evs), sum(pes)
                fb_any = any(fbs)
                row["arms"]["fantasma"] = {"pred": preds[0], "ok": ok, "seconds": sec,
                                           "eval": ev, "prompt_eval": pe, "error": errs[0],
                                           "repeats": repeats, "oks": oks, "preds": preds,
                                           "fallback": fb_any, **last_extra}
                if repeats > 1 and not (all(oks) or not any(oks)):
                    flips["fantasma"] += 1
                score["fantasma"] += ok
                lat["fantasma"].append(sec)
                toks["fantasma"]["eval"] += ev
                toks["fantasma"]["prompt_eval"] += pe
                ok_lists["fantasma"].append(ok)
                if fb_any:
                    guard_fallbacks["fantasma"] += 1
                    guard_fb_n["fantasma"] += 1
                    guard_fb_ok["fantasma"] += int(ok)
                else:
                    guard_clean_n["fantasma"] += 1
                    guard_clean_ok["fantasma"] += int(ok)
            for _arm in ("reformonly", "clear", "random"):
                if _arm not in arms:
                    continue
                oks, preds, secs, evs, pes, errs, fbs = [], [], [], [], [], [], []
                last_extra = {}
                for _r in range(repeats):
                    out, err, sec, ev, pe, extra = _run_ablation_once(_arm, item["question"])
                    pred = pred_number(out)
                    ok = pred is not None and same_number(pred, gold)
                    oks.append(ok)
                    preds.append(pred)
                    secs.append(sec)
                    evs.append(ev)
                    pes.append(pe)
                    errs.append(err)
                    fbs.append(bool(extra.get("fallback", False)))
                    last_extra = extra
                ok = oks[0] if repeats == 1 else (sum(oks) / len(oks) >= 0.5)
                sec = round(sum(secs) / len(secs), 1)
                ev, pe = sum(evs), sum(pes)
                fb_any = any(fbs)
                row["arms"][_arm] = {"pred": preds[0], "ok": ok, "seconds": sec,
                                     "eval": ev, "prompt_eval": pe, "error": errs[0],
                                     "repeats": repeats, "oks": oks, "preds": preds,
                                     "fallback": fb_any, **last_extra}
                if repeats > 1 and not (all(oks) or not any(oks)):
                    flips[_arm] += 1
                score[_arm] += ok
                lat[_arm].append(sec)
                toks[_arm]["eval"] += ev
                toks[_arm]["prompt_eval"] += pe
                ok_lists[_arm].append(ok)
                if fb_any:
                    guard_fallbacks[_arm] += 1
                    guard_fb_n[_arm] += 1
                    guard_fb_ok[_arm] += int(ok)
                else:
                    guard_clean_n[_arm] += 1
                    guard_clean_ok[_arm] += int(ok)
            rows.append(row)
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()

    nn = len(rows)
    acc = {a: round(score[a] / max(1, len(ok_lists[a])), 4) for a in arms}
    stats = {}
    if "fantasma" in arms and "direct" in arms and ok_lists["fantasma"]:
        b = sum(1 for f_, d in zip(ok_lists["fantasma"], ok_lists["direct"]) if f_ and not d)
        c = sum(1 for f_, d in zip(ok_lists["fantasma"], ok_lists["direct"]) if d and not f_)
        stats["fantasma_vs_direct"] = mcnemar(b, c) | {"significant": None}
        stats["fantasma_vs_direct"]["significant"] = stats["fantasma_vs_direct"]["p"] < ALPHA
        stats["bootstrap_fvd"] = bootstrap_diff(ok_lists["fantasma"], ok_lists["direct"], seed=seed)
    if "fantasma" in arms and "hidden" in arms and ok_lists["fantasma"]:
        b = sum(1 for f_, h in zip(ok_lists["fantasma"], ok_lists["hidden"]) if f_ and not h)
        c = sum(1 for f_, h in zip(ok_lists["fantasma"], ok_lists["hidden"]) if h and not f_)
        stats["fantasma_vs_hidden"] = mcnemar(b, c) | {"significant": None}
        stats["fantasma_vs_hidden"]["significant"] = stats["fantasma_vs_hidden"]["p"] < ALPHA
    # v0.04: confronti di ablazione (stessa statistica appaiata).
    def _pair(a: str, b_: str, key: str):
        if a in arms and b_ in arms and ok_lists[a] and ok_lists[b_]:
            bb = sum(1 for x, y in zip(ok_lists[a], ok_lists[b_]) if x and not y)
            cc = sum(1 for x, y in zip(ok_lists[a], ok_lists[b_]) if y and not x)
            stats[key] = mcnemar(bb, cc) | {"significant": None}
            stats[key]["significant"] = stats[key]["p"] < ALPHA
    _pair("fantasma", "reformonly", "fantasma_vs_reformonly")
    _pair("fantasma", "clear", "fantasma_vs_clear")
    _pair("fantasma", "random", "fantasma_vs_random")
    _pair("reformonly", "random", "reformonly_vs_random")
    guard_report = {}
    for a in arms:
        fb = guard_fallbacks.get(a, 0)
        guard_report[a] = {
            "interventions": fb,
            "intervention_rate": round(fb / max(1, nn), 4),
            "clean": {"correct": guard_clean_ok.get(a, 0), "n": guard_clean_n.get(a, 0),
                       "acc": round(guard_clean_ok.get(a, 0) / max(1, guard_clean_n.get(a, 0)), 4)},
            "fallback": {"correct": guard_fb_ok.get(a, 0), "n": guard_fb_n.get(a, 0),
                         "acc": round(guard_fb_ok.get(a, 0) / max(1, guard_fb_n.get(a, 0)), 4)
                         if guard_fb_n.get(a, 0) else None},
            "total": {"correct": score[a], "n": nn,
                      "acc": round(score[a] / max(1, nn), 4)},
        }
    stability = {a: {"flips": flips.get(a, 0), "n": nn,
                     "flip_rate": round(flips.get(a, 0) / max(1, nn), 4)}
                 for a in arms} if repeats > 1 else {a: {"repeats": 1} for a in arms}
    summary = {"tag": tag, "n": nn, "seed": seed, "model": model_name, "arms": list(arms),
               "design": info, "alpha": ALPHA,
               "accuracy": acc, "correct": score,
               "latency": {a: {"mean": round(_mean(lat[a]), 1), "p95": round(_p95(lat[a]), 1)} for a in arms},
               "tokens": toks, "stats": stats,
               "determinism": {"llm_params_requested": llm_requested, "repeats": repeats,
                               "note": "temperature=0 richiesto, non garantito su thinking; "
                                       "usare repeats>=3 + McNemar + IC95%"},
               "guard": guard_report, "stability": stability,
               "v04_salt": "sha256(fantasma-v04-seed)"}
    with open(out_path / f"{tag}_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description="Benchmark GSM8K v0.03 (locale) + v0.04.")
    ap.add_argument("--model", default="gemma4")
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--mode", choices=("random", "stratified"), default="random")
    ap.add_argument("--seed", type=int, default=20261010)
    ap.add_argument("--tag", default="v03")
    ap.add_argument("--outdir", default="outputs/benchmark")
    ap.add_argument("--pool", type=int, default=None)
    ap.add_argument("--no-think", action="store_true",
                    help="think=false su Ollama (veloce su CPU; vale per tutti i bracci)")
    ap.add_argument("--num-predict", type=int, default=None)
    ap.add_argument("--repeats", type=int, default=1,
                    help="v0.04: ripetizioni per braccio (paper: >=3, thinking non deterministico)")
    ap.add_argument("--arms", default="direct,hidden,fantasma",
                    help="v0.04: lista bracci tra direct,hidden,fantasma,reformonly,clear,random")
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--seed-llm", type=int, default=20261010)
    args = ap.parse_args()
    from .llm_ollama import make_ollama_llm

    llm = make_ollama_llm(model=args.model, think=False if args.no_think else None,
                          num_predict=args.num_predict, temperature=args.temperature,
                          seed=args.seed_llm)
    label = args.model + ("[no-think]" if args.no_think else "") + (
        f"[np={args.num_predict}]" if args.num_predict else "") + f"[t={args.temperature}]"
    arm_list = tuple(a.strip() for a in (args.arms or "").split(",") if a.strip()) or ("direct",)
    s = run_benchmark_v03(n=args.n, seed=args.seed, mode=args.mode, llm_fn=llm,
                          model_name=label, outdir=args.outdir, tag=args.tag,
                          pool_n=args.pool, arms=arm_list, repeats=args.repeats)
    print(json.dumps(s, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
