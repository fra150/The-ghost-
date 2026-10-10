# Architettura — Il Fantasma v0.02

## L'idea (una riga)

Il ragionamento intermedio nasce come **codice numerico privato**,
viene riletto dalla **stessa AI** che lo ha generato, e poi **scompare**:
in cache resta solo un blob sigillato la cui chiave viene distrutta.

## v0.01 → v0.02: cosa è cambiato

| aspetto | v0.01 (`pipeline.py`) | v0.02 (`pipeline_v02.py`) |
|---|---|---|
| grezzo | `str` di cifre (`GhostThought.numeric_code`) | `bytes` in `SecretBytes` (mai `str` tranne 1 decode) |
| cache | offuscata (shift cifre da salt, "Cesare a 10") | solo `SealedBlob` (encrypt-then-MAC stdlib) |
| chiave | salt statico | `OneTimeKey` distrutta dopo l'output (crypto-shredding) |
| audit | hash-chain dei contenuti mai salvati | + commitment chiave e `cached_sealed` |
| igiene | nessuna | `ghost_window()` + `mlock` puntuale + amnesia in `finally` |

La v0.01 resta nel repo per confronto (test `test_fantasma.py` intatti).

## Flusso `FantasmaPipelineV02.process()` (stessa interfaccia della v0.01)

1. `input_received` + `gate_decision` (hash in audit).
   Se il gate dice no → chiamata diretta, `ghost_activated=False`.
2. Dentro `ghost_window()`: nonce → HMAC(salt) → 19 cifre ASCII in
   `SecretBytes`; `lock_secret_region`; audit `ghost_activated` (commitment).
3. **Un'unica** `decode_at_boundary()` → prompt `FANTASMA-INTERPRETA`
   alla stessa `llm_fn` → direttiva di riformulazione (senza cifre).
4. `CryptoShredder.seal()` → `SealedBlob` in cache, audit `cached_sealed`;
   wipe del `SecretBytes`, svuotamento store (anche su eccezione).
5. Riformulazione + output finale via `llm_fn`, audit `output_produced`.
6. `shredder.destroy()` (chiave azzerata), cache svuotata,
   audit `ghost_erased`. Ritorna `FantasmaResultV02`
   (`audit_ok`, `memory_empty_after`, `cache_empty_after`, `hygiene`).

## Decisioni 5.x (dr. Bulla)

- **5.1** — stessa AI interpreta (nessun parser esterno).
- **5.2** — in cache solo il sigillato (v0.02; v0.01: offuscato).
- **5.3** — amnesia dopo l'output (memoria e cache vuote).
- **5.4** — amnesia a distruzione di chiave (il ciphertext resta rumore).

## Livelli di garanzia

- **L1 applicativo**: store dichiarati + filesystem. Misura:
  `count_variants_unexpected` + `scan_filesystem`, `R=0` per variante.
- **L2 processo**: RAM del processo. Misura: `scan_process_mem` (/proc su
  Linux) + controlli positivo/negativo (`assert_scanner_sane`).
  Vale solo a hygiene verde; col flusso reale è "ridotto e misurato".
- **L3 provider**: MAI affermato con modello remoto
  (i byte attraversano JSON/HTTP/TLS e l'infrastruttura del provider).

Separazione netta (Sezione 9 del preprint): **garanzia per costruzione**
(L1: tipi che non espongono, wipe strutturale) vs **evidenza misurata**
(L2: scan con mock/canary — mai oltre i confini misurati).
