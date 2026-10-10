# Riproducibilità — setup, test, Docker

## Setup locale (Windows / Linux)

```powershell
copy .env.example .env   # Windows (Linux: cp .env.example .env)
# incolla DEEPSEEK_API_KEY in .env — MAI su git (è in .gitignore)
pip install -r requirements.txt
pytest tests/ -q
```

Atteso: **44 passed in ~5 s** (7 file: 9+3+11+6+3+6+6).
Senza chiave i test usano mock e chiavi finte (`sk-test-finto`).

## Variabili (`.env.example`)

`DEEPSEEK_API_KEY` (obbligatoria per il live), `DEEPSEEK_BASE_URL`
(default `https://api.deepseek.com`), `DEEPSEEK_MODEL` (`deepseek-flash`),
`DEEPSEEK_REASONING_EFFORT=high`, `DEEPSEEK_THINKING=enabled`,
`DEEPSEEK_SYSTEM`.

## Docker

```powershell
docker build -t fantasma:0.1 .
docker run --rm fantasma:0.1                        # test mock
docker run --rm --env-file .env fantasma:0.1        # live (chiave a run-time, mai nell'immagine)
```

Base `python:3.11-slim`, `PYTHONPATH=/app/src`. Nota: `.env` non è copiato
nell'immagine. La misura L2 richiede Linux (/proc) — su Windows L2 non si
afferma (cfr. `docs/SICUREZZA.md`).

## Preprint

Sorgenti `preprint/fantasma_v002_it.tex` / `_en.tex` (5 pagine, 8 figure
TikZ). Richiede `colortbl.sty` (vendored in cartella: TinyTeX senza tlmgr
funzionante — senza quel file non ricompila).

## Benchmark

Richiede `datasets` (`pip install datasets`) + chiave live:

```python
from fantasma.bench_gsm8k import run_benchmark
run_benchmark(n=50, seed=20261010, tag="gsm8k_50")
```
