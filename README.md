# Il Fantasma — The Ghost Layer (v0.02)

Strato di ragionamento interno che **emerge, agisce, scompare**:
un pensiero numerico privato viene generato, interpretato dalla **stessa AI**
che lo ha prodotto, sigillato, e poi cancellato. Resta solo l'audit
(hash, mai contenuti).

> Stato: `v0.2.0-dev` — suite **44 passed**, preprint v0.02 it+en,
> pilota GSM8K-50. Vedi `diario.md` (09/10) e `diario2.md` (10/10).

## Il ciclo in breve (pipeline v0.02)

1. `input` → 2. `gate` (attiva o standby) → 3. pensiero grezzo come **BYTES**
   in `SecretBytes` (mai `str`) dentro `ghost_window()` (no-fork)
2. **stessa AI** interpreta il codice (un'unica `decode_at_boundary`)
3. il grezzo viene sigillato (`CryptoShredder` → `SealedBlob`) e wipato
4. riformulazione + output finale (mai cifre) → 5. **amnesia**:
   chiave distrutta (crypto-shredding), store svuotati, audit `ghost_erased`

Decisioni del dr. Bulla: **5.1** stessa AI interpreta · **5.2** cache solo
sigillata (v0.01: offuscata Cesare, v0.02: encrypt-then-MAC)
· **5.3** amnesia dopo output · **5.4** amnesia a distruzione di chiave.

## Garanzie oneste (L1 / L2 / L3)

- **L1 — applicativo: sì.** Store + filesystem, `R=0` per variante misurato
  (`forensics.count_variants_unexpected`, `scan_filesystem`).
- **L2 — processo: sì con vincoli.** Solo se hygiene verde + scan zero,
  entro confini misurabili (`scan_process_mem` su Linux). Col flusso reale
  (str/JSON/HTTP/TLS) è "ridotto e misurato", **mai garantito**.
- **L3 — provider/terze parti: mai** con modello remoto.

Dettagli: `docs/SICUREZZA.md`, `docs/ARCHITETTURA.md`.

## Struttura

```text
src/fantasma/        framework (14 moduli, vedi docs/MODULI.md)
tests/               7 file, 44 test
outputs/benchmark/   artefatti GSM8K-50 (jsonl + summary)
preprint/            v0.01 (3 pp) + v0.02 (5 pp, 8 figure TikZ), it+en
docs/                architettura, moduli, sicurezza, benchmark, riproducibilità
diario.md / diario2.md   diario di lavoro 09/10 e 10/10/2026
```

Mappa completa: [`REPO_MAP.md`](REPO_MAP.md).

## Quickstart

```powershell
copy .env.example .env   # poi incolla la chiave DeepSeek in .env (MAI su git)
pip install -r requirements.txt
pytest tests/ -q         # 44 passed in ~5s
```

Docker (test mock, senza chiave):

```powershell
docker build -t fantasma:0.1 .
docker run --rm fantasma:0.1
```

Live (con chiave): `docker run --rm --env-file .env fantasma:0.1`
oppure in Python: `make_deepseek_llm()` da `src/fantasma/llm_deepseek.py`
(modello canonico `deepseek-flash`, `reasoning_effort=high`).

## Benchmark GSM8K-50 (pilota, non prova)

| braccio  | accuratezza |
|----------|-------------|
| direct   | 46/50 = 0.920 |
| hidden   | 46/50 = 0.920 |
| fantasma | 47/50 = 0.940 |

Stesso modello, stesso formato `#### <numero>`. Unico divario: item 0
(gold 54: fantasma giusto, gli altri a 27). Dettagli e limiti:
`docs/BENCHMARK.md`.

## Roadmap

- **v0.03**: 200 problemi stratificati sui casi dove il diretto sbaglia;
  la domanda aperta dal giorno 1 resta: il Fantasma migliora davvero
  rispetto al CoT nascosto?

## Sicurezza

`.env` (chiave reale) è in `.gitignore` e **non va mai committato**.
I test usano solo chiavi finte (`sk-test-finto`). Threat model e limiti
dichiarati in `docs/SICUREZZA.md`.
