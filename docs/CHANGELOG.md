# Changelog — Il Fantasma

## v0.06 (17/10/2026) — ri-centratura

Prerequisiti del paper corretto v0.05 («prossima versione»): tre lavori al
centro, zero scaffolding. (1) Nascita uniforme (r.115): `pipeline_v02` e
`codec._to_numeric` non usano piu' `f"{b:03d}"` troncato (~49,5 bit
effettivi, non 63,1): 19 cifre via `secret.digest_to_canonical_19`
(rejection sampling), mai int/str dell'intero codice; determinismo
(salt, nonce, input) intatto. (2) Blinding 128 bit (r.117): in
`crypto.TimedCommitment` la `scrypt_hex` non e' piu' un attributo in
chiaro (storage = hex XOR keystream da chiave monouso); `expire()`
distrugge chiave di finestra E blinding (finally annidati); dopo, la
property solleva `UseAfterDestroyError`: «senso unico dopo T» vale ora
anche sull'artefatto. (3) Ciclo nominato: `CICLO_V006` esportato (input →
CoT → emerge → agisce → scompare → doppio_catenaccio → output; CoT resta
fase muta, output_produced resta la produzione — la consegna avviene dopo
l'amnesia) + meta `fase` sugli eventi chiave; nel cover il wipe del
mapping ora precede il bolt (la ricevuta e' emessa dalla morte).
Test: `tests/test_v06_ri_centratura.py` (4: uniformita' con contrasto
deterministico col vecchio schema, determinismo (salt, nonce, input),
ordine del ciclo su run con cover, ricevute dalle morti + catena
prev→entry) + `test_red_freeze.py` aggiornato (dopo expire `scrypt_hex`
solleva). Suite: 147 passed (142 + 5).

## Correzione overcover (17/10/2026)

Chiusura del gap citato nel paper corretto v0.05 (§6): aggiunti
`overcover_ref.py` (riferimento falsi positivi del criterio di copertura,
protocollo deterministico seed 20261010, 20 000 numeri per lunghezza →
conteggi esatti 2030/1956/1999 = 10,15%/9,8%/10,0%) e `tests/test_overcover.py`
(51 test, incluso il corpus reale: 0 sostituzioni strict sui 50 GSM8K).
Suite: 142 passed (91 + 51). CLI: `PYTHONPATH=src python -m fantasma.overcover_ref`.

## v0.05 (16/10/2026) — cover pre-CoT

Cover degli identificatori prima di ogni chiamata al modello
(solo placeholder al modello, valori veri mai fuori macchina):
`pii_cover.py` (regex+checksum stdlib, nessun modello esterno, nessuna
dipendenza nuova), placeholder `[PII_TAG_N]` stabili e disgiunti dal codice
a 19 cifre e dal formato `####`, mapping in bytearray wipabili inchiodato
al BoltRegistry (`cover:<uid>`, wipe garantito anche sui raise), residual
scan sul coperto, restore in locale. `pipeline_v02` con `cover_pii=True`
(default `False`, invariata); strato open-class solo via modelli open in
locale, sperimentale e opt-in. Suite: 91 passed (76 + 15 cover).

## v0.04 (13/10/2026) — P0 scientifico

Disegno pre-registrato a 6 bracci (`docs/PREREG_v004.md`): direct, hidden,
fantasma, reformonly, clear (pensiero-in-chiaro), random (cifre-casuali).
I run v0.04 non sono confrontabili con v0.03 (prompt e guard diversi).

- `reform_guard.py` (nuovo): gate allowlist Call-1→Call-2, normalizzazione
  numeri (`160.000`→`160000`, `160 mila`→`160000`, parole italiane comuni),
  blocco `####`/numeri nuovi lunghi, 1 retry + fallback Direct contato a
  parte, reporting a 3 colonne (pulite/fallback/totale).
- `arms.py` (nuovo): `run_arm_reformonly_v04`, `run_arm_clear_v04`,
  `run_arm_random_v04` + `derived_code()` (HMAC + rejection sampling).
- Determinismo: `temperature=0.0, top_p=1.0, seed=20261010` richiesti
  (mai garantiti su thinking) su DeepSeek + Ollama; `repeats>=3`,
  flip-rate, McNemar + bootstrap su tutte le coppie; params registrati.
- Codice canonico unbiased: `digest_to_canonical_19` / `random_canonical_19`
  da `token_bytes` + rejection sampling, mai int/str dell'intero codice;
  `validate_canonical_19` sul buffer; `SecretBytes` blocca int/index/float.
- `secure_wipe_buffer()` centralizzato (refactor, non claim L2);
  `scrub_traceback()` limitato (try/except per frame, solo DECREF).
- Prompt Call-1 rigido condiviso (`CALL1_RIGID_TAIL`) in codec,
  pipeline_v02 (con fallback), pipeline_reformonly, bracci.
- Errata v0.03 applicata ai `.tex` (`preprint/ERRATA_v003.md`): data
  13/10/2026, Fig.5 riscritta (copie in chiaro in memoria liberata ma non
  sovrascritta), `T1+microtype`, NIST con DOI.
- Suite: 68 passed (`tests/test_v04_guard.py`: 15 nuovi).

## v0.03 (13/10/2026) — controllo, fallimenti, leakage, related

Braccio ReformOnly, failure analysis (classi A/B/C/D, error-mode 1/50),
T4 leakage (ROUGE think 0.308 vs domanda 0.733), related verificato,
preprint v0.03 it+en a 4 bracci. Trovato leak ID36 → fix v0.04.

## v0.02 (10/10/2026) — misura L1/L2, GSM8K-50, preprint 5 pagine

SecretBytes/CryptoShredder/hygiene/forensics, Docker L2, scrypt + 19 cifre
+ SecretRegion (3 rossi), benchmark 46/46/47 su 50, suite 44 passed.
