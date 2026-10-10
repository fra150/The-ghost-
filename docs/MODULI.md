# Moduli — riferimento (`src/fantasma/`)

Versione package: `0.2.0-dev`. Tutti i simboli sono riesportati in `__init__.py`.

## Nucleo v0.02

- **`secret.py`** — il grezzo non esiste mai come `str`.
  `SecretBytes` (backing `bytearray`, wipe a singola `0x00`, `__repr__`
  mascherato, `str`/`bytes`/pickle bloccati, `decode_at_boundary()` unica
  conversione consentita, `commitment()` sha256 per audit).
  `OneTimeKey` (32 byte da `secrets`, `commitment`, `destroy()`; `region()`
  per la copia di lavoro). `SecretRegion` (context manager: memset via
  ctypes in `__exit__` **sempre**, anche su eccezione/return).
- **`crypto.py`** — `seal_with_key` / `open_with_key` (encrypt-then-MAC
  stdlib in-place, più wipabile di OpenSSL-C). `scrypt_commitment`
  (N=2¹⁴, r=8, p=1; ~44 ms/tentativo). `TimedCommitment` (finestra T:
  verificabile via tag keyed, poi solo scrypt one-way). `SealedBlob`
  (ciphertext + nonce + tag). `CryptoShredder` (chiave monouso +
  `key_commitment` + `destroy()`). Costanti: `CODE_DIGITS_CANONICAL=19`
  (63,1 bit), `CODE_DIGITS_LEGACY=13`. Helper `entropy_bits`,
  `enumerate_years`.
- **`pipeline_v02.py`** — `FantasmaPipelineV02.process()` (vedi
  ARCHITETTURA), `FantasmaResultV02` (`algo =
  "stdlib-encrypt-then-MAC-SHA256+HMAC-SHA256/scrypt-audit"`),
  `default_mock_llm_v02` (stessa-AI simulata: somma cifre % 3).
- **`ghost_window.py`** — `ghost_window()` (guard rail no-fork Python,
  non barriera: il fork accidentale è vietato, spawn consigliato),
  `assert_no_fork_in_window`, `recommended_start_method`,
  `scrub_frame_locals` (best-effort: su frame sospesi non si propaga —
  vale `finally` + `traceback=None`), `release_traceback`,
  `install_scrubbing_excepthook`. Mai traceback loggati dentro la finestra.
- **`hygiene.py`** — `apply_process_hygiene()` (report; `RLIMIT_CORE=0`
  dove possibile), `lock_secret_region` / `unlock_secret_region`
  (mlock puntuale con report per-pagina: "regione designata protetta",
  NON "nessuna copia in swap"), alias `lock_buffer`/`unlock_buffer`.
- **`forensics.py`** — `generate_runtime_canary` (solo runtime, default
  19 cifre), `needle_variants` (raw, utf16le/be, hex, base64, int-decimal,
  int-hex — con regola "codice mai intero"), `count_needle_in_stores` /
  `count_variants_in_stores`, `count_unexpected` /
  `count_variants_unexpected` (trovate − legittime = **R**),
  `scan_process_mem` (/proc su Linux; `gc.get_objects` NON vede bytes/str),
  `scan_filesystem` (cwd + temp), `compute_R`, `evaluate_claim`
  (con guardia hygiene: L2 solo se verde), `assert_scanner_sane`
  (controlli positivo/negativo obbligatori).

## Strato v0.01 (tenuto per confronto)

- **`pipeline.py`** — `FantasmaPipeline` / `FantasmaResult` /
  `default_mock_llm`: flusso 1→8 con cache offuscata + amnesia 5.3.
- **`gate.py`** — `HeuristicGate.should_activate()` →
  `GateDecision(active, score, reason)`.
- **`codec.py`** — `PrivateNumericCodec.generate()` → `GhostThought`
  (uid, numeric_code, vector), `build_interpret_prompt()`,
  `INTERPRET_MARKER` (`FANTASMA-INTERPRETA`).
- **`memory.py`** — `EphemeralMemory` (put/forget/selective_reset),
  `ObfuscatedCache` (seal/clear; shift cifre da salt),
  `obfuscate_numeric` / `deobfuscate_numeric`.
- **`audit.py`** — `AuditLogger` (hash-chain: `log`, `verify`,
  `hash_text`), `AuditEvent`. Solo hash, mai contenuti.

## Integrazione e misura

- **`llm_deepseek.py`** — `load_env`, `get_config`, `make_deepseek_llm`
  (OpenAI-compatibile; default `deepseek-flash`, `reasoning_effort=high`,
  `thinking=enabled`; normalizzazione nome display), `ping`.
- **`bench_gsm8k.py`** — `run_benchmark(n, seed, arms)`:
  `direct` (1 chiamata) vs `hidden` (CoT privato nascosto) vs `fantasma`
  (pipeline v0.02); scoring exact-match su `#### <numero>`;
  artefatti JSONL + summary in `outputs/benchmark/`.
