# Benchmark GSM8K — protocollo e numeri

Perché GSM8K: il più popolare per il ragionamento con risposte verificabili
senza giudice (numero esatto dopo `####`). Il Fantasma "incornicia bene":
qui l'incorniciatura si misura in accuratezza exact-match a parità di modello.

## Protocollo (`src/fantasma/bench_gsm8k.py`)

- 50 problemi dal test set (`openai/gsm8k:main`), seed `20261010`.
- Stesso modello (`deepseek-flash`), stesso formato finale
  (`Rispondi con il numero finale nel formato: #### <numero>`).
- Tre bracci: **direct** (1 chiamata) · **hidden** ("ragiona in privato,
  mostra solo `####`") · **fantasma** (pipeline v0.02 completa).
- Scoring: regex su `####`, normalizza virgole, confronto numerico col gold.
- Per item: gold, pred, ok, ghost, audit, mem/cache vuote, tempi.
  Artefatti: `outputs/benchmark/gsm8k_50.jsonl` + `gsm8k_50_summary.json`
  (+ `pilot5.*` della prima prova).

## Risultati 10/10/2026

| braccio | corretti | accuratezza | tempo |
|---|---|---|---|
| direct | 46/50 | 0.920 | ~2.6 s |
| hidden | 46/50 | 0.920 | ~2.8 s |
| fantasma | 47/50 | 0.940 | ~10.7 s (2 chiamate + sigillo) |

Ghost 48/50 (2 standby legittimi), audit 50/50, mem/cache vuote 50/50.
Unico divario: item 0 (gold 54 — fantasma giusto, gli altri a 27).
Nessun caso perso dal fantasma da solo.

## Limiti (dichiarati)

Segnale **debole**: pilota n=50, non prova. Il passo v0.03 è
**200 problemi stratificati sui casi dove il diretto sbaglia**, per
rispondere alla domanda aperta dal giorno 1: il Fantasma migliora davvero
rispetto al CoT nascosto?
