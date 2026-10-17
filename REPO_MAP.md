# Repository Map — Il Fantasma (v0.02)

Mappa dei file sotto git. Esclusi: `.env` (chiave reale, mai su git),
`.opencode/` (tooling), `.benchmarks/` (vuoto), cache Python.

```text
il  fatasma/
├── README.md                  questa repo in una pagina
├── REPO_MAP.md                questa mappa
├── diario.md                  diario 09/10/2026 — concept, v0.01, DeepSeek live, preprint v0.01
├── diario2.md                 diario 10/10/2026 — v0.02, Docker L2, rossi pre-print, GSM8K-50
├── requirements.txt           pytest, openai, python-dotenv, cryptography (AEAD futura)
├── Dockerfile                 python:3.11-slim, PYTHONPATH=/app/src, CMD pytest (chiave via --env-file)
├── .env.example               template config (nessun segreto) — copiare in .env
├── .gitignore                 .env, cache, .opencode/, .benchmarks/
│
├── src/fantasma/              framework — v0.2.0-dev
│   ├── __init__.py            export pubblici + __version__
│   ├── pipeline_v02.py        pipeline canonica (.process(), ciclo CICLO_V006, cover, amnesia)
│   ├── pipeline.py            pipeline v0.01 (cache offuscata Cesare, tenuta per confronto)
│   ├── secret.py              SecretBytes / OneTimeKey / SecretRegion (base L1+L2)
│   ├── crypto.py              seal/open encrypt-then-MAC, scrypt commitment, TimedCommitment (+ blinding)
│   ├── hygiene.py             apply_process_hygiene, lock/unlock regione (mlock puntuale)
│   ├── forensics.py           canary runtime, varianti, scan mem/FS, R, evaluate_claim
│   ├── ghost_window.py        finestra no-fork, scrub frame, release_traceback
│   ├── gate.py                HeuristicGate / GateDecision (attiva o standby)
│   ├── codec.py               PrivateNumericCodec / GhostThought / INTERPRET_MARKER (v0.06: cifre uniformi)
│   ├── memory.py              EphemeralMemory / ObfuscatedCache (v0.01)
│   ├── audit.py               AuditLogger hash-chain (solo hash, mai contenuti)
│   ├── llm_deepseek.py        adapter DeepSeek-V4.1-Flash (make_deepseek_llm, ping)
│   └── bench_gsm8k.py         harness GSM8K: direct vs hidden vs fantasma
│
├── tests/                     44 test totali
│   ├── test_fantasma.py       9 — pipeline v0.01 (originali intatti)
│   ├── test_llm_deepseek.py   3 — adapter mockato (originali intatti)
│   ├── test_forensics.py      11 — varianti, R, claim, scanner sano
│   ├── test_claim_integrity.py 6 — integrità claim L1/L2
│   ├── test_pipeline_v02.py   3 — pipeline v0.02
│   ├── test_v02_hardening.py  6 — scrypt, memset, int/hex/b64, FS scan, loopback, scrub
│   └── test_red_freeze.py     6 — i tre rossi pre-print (costo scrypt, 19 cifre+T, SecretRegion)
│
├── outputs/
│   ├── benchmark/             gsm8k_50.jsonl + _summary, pilot5.* (primi 200 char domanda, pred, ok)
│   ├── genera_fix.py / prezzi_fix.py / implementa_spec.py   script dai casi veri
│   └── live_code_impl.md / live_code_output.md              report casi veri (4 bug trovati)
│
├── preprint/
│   ├── fantasma_it/en.tex+.pdf        v0.01, 3 pagine
│   ├── fantasma_v002_it/en.tex+.pdf   v0.02, 5 pagine, 8 figure TikZ
│   └── colortbl.sty                   vendored (TinyTeX senza tlmgr funzionante)
│
└── docs/
    ├── ARCHITETTURA.md      v0.01→v0.02, flusso, decisioni 5.x, livelli L1/L2/L3
    ├── MODULI.md            riferimento per modulo
    ├── SICUREZZA.md         threat model, 9 scoperte, 3 rossi, cosa NON è garantito
    ├── BENCHMARK.md         protocollo GSM8K, numeri, limiti
    └── RIPRODUCIBILITA.md   setup, test, Docker, env
```

## Dove guardare per…

- capire il flusso: `src/fantasma/pipeline_v02.py` + `docs/ARCHITETTURA.md`
- capire il wipe: `src/fantasma/secret.py` (docstring `decode_at_boundary`)
- capire la misura: `src/fantasma/forensics.py` (`evaluate_claim`, `compute_R`)
- rifare i numeri: `src/fantasma/bench_gsm8k.py` + `docs/BENCHMARK.md`
- ricompilare il paper: `preprint/fantasma_v002_it.tex`
