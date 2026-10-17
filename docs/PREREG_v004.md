# Pre-registrazione v0.04 — disegno a 6 bracci con guard e ripetizioni

Data: 13/10/2026. Seed campione: 20261010. Modello: deepseek-flash
(DeepSeek-V4.1-Flash), reasoning_effort=high, thinking abilitato.
Parametri richiesti: temperature=0.0, top_p=1.0, stream=False, seed=20261010
(RICHIESTI, non garantiti su thinking — vedi nota determinismo).

## Bracci (stesso modello, stesso formato `#### N`)

1. direct — 1 chiamata domanda+formato.
2. hidden — 1 chiamata con istruzione di ragionamento privato.
3. fantasma — 2 chiamate + sigillo (pipeline_v02 con guard v0.04).
4. reformonly — 2 chiamate senza sigillo, stesso prompt rigido + guard.
5. clear (pensiero-in-chiaro) — 2 chiamate, Call-2 vede codice + riformulazione.
6. random (cifre-casuali) — 2 chiamate, codice CSPRNG scollegato dalla domanda.

Tutti i bracci 3-6 usano: prompt Call-1 rigido (CALL1_RIGID_TAIL),
guard allowlist (reform_guard.py) con max 1 retry, fallback Direct
dichiarato e contato a parte. I run v0.04 NON sono confrontabili con v0.03
(prompt e guard diversi): rieseguire tutti i bracci con lo stesso guard.

## Campione

- Fase A (pilota): n=50, seed 20261010, stessi 50 della v0.03 per confronto interno.
- Fase B (prova): n=200 stratificati sugli hard (sweep direct su pool test,
  primi 200 fallimenti; se <200, fill_random dichiarato).

## Ripetizioni e statistica (alfa=0.05)

- repeats >= 3 per braccio su ogni item (thinking non deterministico anche a
  temperature=0). Accuratezza = media su tutte le chiamate; stabilita' = flip
  rate (item con esiti non unanimi). McNemar appaiato (chi2-cc, esatto se
  b+c<25) + bootstrap 10k IC95% per ogni coppia pre-specificata:
  fantasma-vs-direct, fantasma-vs-hidden, fantasma-vs-reformonly,
  fantasma-vs-clear, fantasma-vs-random, reformonly-vs-random.

## Reporting obbligatorio per braccio

- Accuratezza a 3 colonne: pulite / fallback / totale + tasso di intervento
  del guard. Mai mescolare fallback nel totale senza dichiararlo.
- Tasso di trafilamento con e senza guard (formato `####`, numeri nuovi).
- Latenza mean/P95, token eval/prompt_eval, params richiesti registrati.

## Regole di decisione pre-specificate

- H0 (sigillo): fantasma == reformonly entro IC95% e McNemar p>=0.05.
- Contenuto vs computo: se random == fantasma -> conta solo extra-compute;
  se random < fantasma -> il contenuto conta.
- Costo del blinding: se clear > fantasma -> nascondere costa accuratezza.
- Error-mode due-call: deriva B su >=1/50, riportare classe e ID.

## Artefatti

`{tag}.jsonl` (per-item con oks/preds/guard/fallback), `{tag}_summary.json`
(con accuracy/guard/stability/determinism/stats), trace Call-1 per T4.
