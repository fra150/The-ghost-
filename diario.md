# Diario del Fantasma — 09/10/2026

## Mattina — la concept note (Catania, 7 ottobre → Bologna, 9 ottobre)
Si parte dalla bozza v0.1 di Francesco: il Fantasma come strato di ragionamento
interno che emerge, agisce, scompare. Pensiero in codice numerico privato
(es. `0984567345679`), poi cancellato. Niente codice in questa fase, solo
ragionamento insieme. Smontiamo l'idea in tre letture — tecnica, filosofica,
poetica — e restano sul tavolo i nodi 5.1–5.4 più il paradosso etico:
chi progetta il gate decide come il modello ragiona.

## Mezzogiorno — il framework prende piede
Decisione: provarle tutte, si scrive codice. Solo `src` + `Dockerfile` + test.
Nasce `src/fantasma`: `gate.py`, `codec.py`, `memory.py`, `audit.py`,
`pipeline.py`. Meccanismo 1→6, audit a hash-chain senza contenuti.
Primi test: 8/8 verdi in locale e su Docker (`fantasma:0.1`).

## Le tre decisioni di Francesco
- **5.1** — sarà la stessa AI a interpretare il codice. Via il parser esterno:
  il numerico viene riconsegnato allo stesso modello (prompt `FANTASMA-INTERPRETA`).
- **5.2** — finisce in cache ma offuscato. Il grezzo vive solo nel giro;
  in cache va solo lo shift delle cifre derivato dal salt.
- **5.3** — sputa l'output e non serve ricordare. Amnesia di progetto:
  memoria e cache vuote dopo ogni ciclo.
- Suite aggiornata: 9/9 verdi.

## Pomeriggio — DeepSeek-V4.1-Flash
L'utente porta lo snippet OpenAI-compatibile. Si crea `.env` + `.env.example`
+ `.gitignore`, adapter `llm_deepseek.py` (modello canonico `deepseek-flash`,
`reasoning_effort=high`, `thinking=enabled`), normalizzazione del nome display.
Test mockati: 12/12 verdi. Primo ping live: 401, chiave rifiutata (`****2f1e`).
Chiave cambiata → ping ok: "Hello! How can I help you today?"
Primo giro Fantasma live: ghost attivo, stessa-AI attiva, mem/cache vuote, audit ok.

## I 4 casi veri + il codice
Tutti e 4 live, tutti con Fantasma attivo: decisione Milano/Catania, messaggio al
collaboratore (il migliore, pronto da inviare), brief web app, paradosso etico
(la AI sposta il fuoco su consenso e contestabilità). Pattern: incornicia
benissimo, chiude a metà.
Test di codice: 4 bug nascosti trovati tutti (default mutabile, `range(len+1)`,
divisione per zero, nomi bugiardi). Passo 1 produce la specifica, passo 2
391 righe di implementazione. Prima esecuzione rossa per un assert troppo severo
(chiavi extra), fix di una riga, poi `Tutti i test sono passati.`
Artefatti in `outputs/`.

## Sera — il preprint v0.01
Bologna, 09/10/2026, dr. Francesco Bulla. LaTeX italiano + inglese con TikZ:
ciclo del Fantasma, curva privacy/verificabilità, roadmap v0.01 → v0.1 → v1.0.
Nota "bozza locale" rimossa su richiesta. `preprint/fantasma_it.pdf` e
`fantasma_en.pdf`, 3 pagine ciascuno.
