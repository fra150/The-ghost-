"""
Il Fantasma v0.05 (revisione corretta) — overcover_ref.py.

Riferimento per la misura di over-cover (falsi positivi del criterio di
copertura su numeri nudi), consegnato con il documento di correzione e ora
incluso nel repository. Riproduce i valori citati nel paper (§6):

  - 11 cifre: 2030/20000 = 10,15%   (controllo P.IVA)
  - 13 cifre: 1956/20000 = 9,78%    (controllo Luhn)  -> "9,8%" nel paper
  - 16 cifre: 1999/20000 = 9,995%   (controllo Luhn)  -> "10,0%" nel paper

Protocollo (deterministico e riproducibile):
  per ogni lunghezza n in (11, 13, 16):
    rng = random.Random(20261010)        # seed fisso, generatore NUOVO per n
    per 20000 volte: s = str(rng.randint(10**(n-1), 10**n - 1))
    conta i casi con checksum valido: piva_ok per n=11, luhn_ok per n=13/16

I conteggi sono esatti e stabili (MT19937 di CPython, stesso flusso di
estrazioni a parita' di seed); le percentuali stampate nel paper arrotondano
9,78 -> 9,8 e 9,995 -> 10,0 (mezza unita' in su).

Inoltre `count_strict_spans` misura le sostituzioni che `find_cover_spans`
farebbe su un corpus: sui 50 problemi GSM8K del benchmark la misura e' 0
(il benchmark non e' alterato perche' cover_pii=False nei run).

Uso CLI (dalla radice del repo):
    PYTHONPATH=src python -m fantasma.overcover_ref [--corpus FILE.jsonl]
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from .pii_cover import find_cover_spans, luhn_ok, piva_ok

__all__ = [
    "SEED",
    "N_DRAWS",
    "LENGTHS",
    "EXPECTED_COUNTS",
    "count_false_positives",
    "reference_rates",
    "count_strict_spans",
    "main",
]

SEED = 20261010
N_DRAWS = 20000
LENGTHS = (11, 13, 16)

# Conteggi attesi col protocollo sopra (deterministici; vedi docstring).
EXPECTED_COUNTS = {11: 2030, 13: 1956, 16: 1999}


def _checker(length: int):
    return piva_ok if length == 11 else luhn_ok


def count_false_positives(length: int, n_draws: int = N_DRAWS, seed: int = SEED) -> int:
    """Quanti numeri nudi di `length` cifre superano il criterio (falsi positivi).

    Intervallo pieno [10**(length-1), 10**length - 1]: niente zeri iniziali,
    distribuzione uniforme nell'intervallo. Generatore nuovo a ogni chiamata
    (lo stesso stream riparte per ogni lunghezza).
    """
    rng = random.Random(seed)
    check = _checker(length)
    lo, hi = 10 ** (length - 1), 10 ** length - 1
    hits = 0
    for _ in range(n_draws):
        if check(str(rng.randint(lo, hi))):
            hits += 1
    return hits


def reference_rates(n_draws: int = N_DRAWS, seed: int = SEED) -> dict[int, dict]:
    """Tabella del riferimento: {lunghezza: {hits, draws, pct}} (pct non arrotondata)."""
    out: dict[int, dict] = {}
    for n in LENGTHS:
        hits = count_false_positives(n, n_draws=n_draws, seed=seed)
        out[n] = {"hits": hits, "draws": n_draws, "pct": 100.0 * hits / n_draws}
    return out


def count_strict_spans(texts) -> dict:
    """Sostituzioni che la cover strict (`find_cover_spans`) farebbe sul corpus.

    Conteggi aggregati per tag, mai contenuto (principio di audit del paper).
    """
    total = 0
    by_tag: dict[str, int] = {}
    n_texts = 0
    for t in texts:
        n_texts += 1
        for _s, _e, tag, _raw in find_cover_spans(t or ""):
            total += 1
            by_tag[tag] = by_tag.get(tag, 0) + 1
    return {"texts": n_texts, "total": total, "by_tag": by_tag}


def _extract_texts_from_jsonl(path: Path) -> list[str]:
    keys = ("question_full", "question", "prompt", "input")
    texts: list[str] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            for k in keys:
                if isinstance(row.get(k), str):
                    texts.append(row[k])
                    break
    return texts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Riferimento over-cover (falsi positivi).")
    ap.add_argument("--corpus", type=Path, default=None,
                    help="JSONL con i testi (campo question_full/question/prompt/input)")
    args = ap.parse_args(argv)

    rates = reference_rates()
    print(f"Riferimento over-cover — seed {SEED} — {N_DRAWS} numeri per lunghezza")
    for n in LENGTHS:
        r = rates[n]
        print(f"  {n:2d} cifre: {r['hits']}/{r['draws']} = {r['pct']:.2f}% "
              f"(atteso {EXPECTED_COUNTS[n]})")
    if args.corpus is not None:
        texts = _extract_texts_from_jsonl(args.corpus)
        rep = count_strict_spans(texts)
        print("Corpus:", str(args.corpus), "->", json.dumps(rep, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
