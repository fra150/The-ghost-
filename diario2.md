# Diario del Fantasma — 10/10/2026 (v0.02)

## Mattina — si riparte dal diario
Riletto `diario.md` del 09/10: concept, framework `src/fantasma`, decisioni 5.1/5.2/5.3,
DeepSeek `deepseek-flash` live, 4 casi veri + 4 bug, preprint v0.01 it/en.
Cartella verificata: `src, tests, outputs, preprint, Dockerfile, .env`.
Decisione: lavorare alla v0.02 partendo dai due consigli portati da Francesco.

## I due consigli — cosa ne pensiamo
Entrambi dicono che la "scomparsa" v0.01 è dichiarazione, non garanzia.
Il primo dà l'architettura (threat model, crypto-shredding, stateless, locale, test, metrica).
Il secondo dà i numeri (3 copie baseline, 4 in bytearray, 10 al prompt, 8 dopo wipe, 31 coi letterali)
e i livelli L1/L2/L3. Sintesi nostra: L1 sì oggi, L2 sì con vincoli, L3 mai con provider remoto.
5.2 da riscrivere (Cesare a 10, non cifratura), 5.1 paga in verificabilità, R come metrica.

## Primo giro di codice — le 4 primitive
- `src/fantasma/secret.py`: SecretBytes in bytearray wipabile, repr mascherato, str/pickle bloccati,
  decode_at_boundary una sola volta, OneTimeKey con commitment. Poi passati a singola 0x00
  (una basta, niente elisione in Python).
- `src/fantasma/crypto.py`: prima XOR+HMAC stdlib, poi AES-256-GCM via cryptography,
  poi misura che OpenSSL copia in C e si torna a stdlib in-place (più wipabile).
  Finale: encrypt-then-MAC stdlib + scrypt per audit + chiave random con memset.
- `src/fantasma/hygiene.py`: tolto mlockall (troppo, OOM), solo mlock puntuale
  con report per-pagina. RLIMIT_CORE=0 dove possibile.
- `src/fantasma/forensics.py`: canary solo runtime, store L1 portabile, /proc/mem su Linux,
  varianti raw/utf16le-be/hex/base64/int-decimal/int-hex, R = trovate - legittime,
  evaluate_claim con guardia hygiene, scan_filesystem su cwd+temp.
- `src/fantasma/pipeline_v02.py`: stessa .process(), dentro ghost_window, lock regione,
  una decode, blob sigillato, wipe+destroy, audit solo commitment.
- `src/fantasma/ghost_window.py`: guard rail no-fork Python (non barriera), spawn consigliato,
  scrub version-gate 3.13 + release_traceback, mai traceback loggati dentro.

## Le scoperte guardando prima di dichiarare
1. decode lascia str non wipabili (str/JSON/HTTP/TLS): L2 non sarà R=0 col flusso reale.
2. gc.get_objects non vede bytes/str: heap-scan via gc sempre 0 anche col segreto vivo.
   Serve /proc/mem su Linux o store dichiarati + controlli positivo/negativo.
3. bytes(canary) è lo stesso oggetto: per la seconda copia serve bytearray->bytes.
4. Scrub su frame sospesi non si propaga (0 verificato anche su 3.13): vale finally + traceback=None.
5. Fork duplica via COW: vietato l'accidentale nella finestra, dichiarato il resto.
6. int('098..') perde lo zero: serve regola "codice mai intero" + varianti int.
7. Commitment HMAC su 13 cifre = 43 bit (~17 min/GPU): passato a scrypt (~17400 anni).
8. Chiave in bytes non si azzera: solo bytearray + memset; drop è igiene, non cancellazione.
9. del+gc libera senza azzerare: L1 a 0 vale per gli store, non per la RAM.

## Misura Docker L2 (Linux 6.6 WSL2, Python 3.11.17, memlock=-1, IPC_LOCK)
Hygiene verde, lock 19 byte ok. Canary 19 cifre: baseline raw 2 regioni,
dopo decode 4, dopo prompt 4, dopo wipe+del+gc ancora 4. utf16/hex a 1,
base64 1->2, int-hex 1->2. Prova che L2 è "ridotto e misurato", mai garantito.
Su Windows 10.0.26200, Python 3.13.13: hygiene rossa, /proc assente,
L2 correttamente non affermato.

## Test — tutto in tests/
- test_fantasma.py 9/9, test_llm_deepseek.py 3/3 (i 12 originali intatti).
- test_forensics.py 11, test_claim_integrity.py 6, test_pipeline_v02.py 3,
  test_v02_hardening.py 6 (scrypt, memset, int/hex/b64, FS scan, loopback 127.0.0.1, scrub).
- Finale: 38 passed in ~5s. requirements +cryptography (futura AEAD).

## Sezione 9 pronta da congelare
Garanzia per costruzione separata da evidenza misurata con mock.
L1 = store + filesystem, R=0 per variante. L2 solo se hygiene verde + scan zero,
entro confini misurabili. L3 mai. Numeri concreti dentro, OS/Python dichiarati.
Prossimo: chiudere v0.02, aggiornare PDF, poi domanda aperta dal giorno 1 —
il Fantasma migliora davvero rispetto al CoT nascosto?

## Pomeriggio — i tre rossi pre-print (chiusi con codice)
1. Numero scrypt etichettato: ~44ms/tentativo a regime (non prima chiamata),
   ~14.000 anni/core su 10^13, ma bandwidth-bound: 1 GPU ~3,2 anni a 13 cifre,
   100 GPU ~12 giorni. Il per-core non è la difesa, la difesa è l'entropia.
2. Codice canonico 19 cifre (63,1 bit) + TimedCommitment con finestra T:
   verificabile entro T via tag keyed, solo scrypt one-way dopo expire.
   Test: costo misurato, 13 enumerabile vs 19 fuori portata, scadenza per tempo e per chiamata.
3. SecretRegion con memset via ctypes in __exit__ sempre (return/eccezione comprese).
   expose_mutable resta API basso livello, la pipeline passa dal manager.
   Bug trovato scrivendo: la prima region esponeva il buffer interno e lo azzerava
   al primo seal — ora lavora su copia, chiave viva fino a destroy().
- Nuovo `tests/test_red_freeze.py` con 6 test. Totale suite: 44 passed.

## Sera — live con DeepSeek e casi veri
Ping ok, chiave …7b39, modello deepseek-flash. Standby 'ciao' diretto in italiano.
Complesso v0.01 e v0.02: ghost attivo, stessa-AI, audit ok, amnesia ok.
v0.02 mostra cached_sealed al posto di cached_obfuscated, output più operativo.
Milano/Catania live: scenari A/B/C ibrido con tabella e criteri di verifica.
Collaboratore live: tono diretto sui fatti e morbido sul giudizio, pronto da inviare.
File temporanei live_* rimossi dopo l'uso.

## Notte — benchmark GSM8K a 50 (harness nuova)
`src/fantasma/bench_gsm8k.py`: 50 problemi test set, seed 20261010, tre bracci
stesso modello e stesso formato ####. Direct 46/50 = 0.920 (2.6s),
hidden 46/50 = 0.920 (2.8s), fantasma 47/50 = 0.940 (10.7s, 2 chiamate + sigillo).
Ghost 48/50 (2 standby legittimi), audit 50/50, mem/cache vuote 50/50.
Unico divario: item 0, gold 54, fantasma giusto, gli altri a 27. Nessun caso
perso da solo. Segnale debole dichiarato: pilota, non prova.
Artefatti in `outputs/benchmark/`: gsm8k_50.jsonl + summary, pilot5.
Prossimo: 200 stratificati sui casi dove il diretto sbaglia (v0.03).

## Preprint v0.02 it+en con colori (data 10/10/2026, dr. Francesco Bulla)
`preprint/fantasma_v002_it.tex/.pdf` e `_en`, 5 pagine ciascuno, 8 figure TikZ:
ciclo, L1/L2/L3, entropia, finestra T, barre L2 Docker, barre GSM8K,
curva privacy, roadmap v0.03. Palette blu/verde/ambra/rosso, tabelle con header.
Intoppo onesto: TinyTeX senza colortbl.sty e tlmgr muto — pacchetto generato
dai sorgenti CTAN e tenuto in cartella, senza quello non ricompila.
Sezione 9 trascritta dai test: garanzia per costruzione separata dall'evidenza,
L2 misurato mai garantito, L3 mai affermato.
