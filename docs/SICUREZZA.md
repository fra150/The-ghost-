# Sicurezza — threat model e limiti dichiarati

## Threat model (dalla prima recensione)

Threat model esplicito, crypto-shredding al posto dell'offuscamento,
stateless per giro, `str` mai per i segreti, test forensi, metrica R.
La "scomparsa" v0.01 era **dichiarazione**: dalla v0.02 è
**costruzione + misura**.

## Le 9 scoperte (guardando prima di dichiarare)

1. `decode` crea `str` non wipabili (str/JSON/HTTP/TLS): L2 non sarà R=0
   col flusso reale.
2. `gc.get_objects` non vede bytes/str: heap-scan via gc sempre 0 anche
   col segreto vivo — serve /proc su Linux o store dichiarati.
3. `bytes(canary)` riusa lo stesso oggetto: la seconda copia richiede
   passaggio per `bytearray`.
4. Lo scrub su frame sospesi non si propaga (verificato 0 anche su 3.13):
   vale `finally` + `traceback=None`.
5. Il fork duplica via COW: vietato l'accidentale nella finestra,
   dichiarato il resto.
6. `int('098…')` perde lo zero iniziale: regola "codice mai intero".
7. Commitment HMAC su 13 cifre ≈ 43 bit (~17 min/GPU): passato a scrypt
   + codice canonico a 19 cifre (63,1 bit).
8. Chiave in `bytes` non si azzera: solo `bytearray` + memset;
   il drop è igiene, non cancellazione.
9. `del`+gc libera senza azzerare: L1 a 0 vale per gli store, non per la RAM.

## I tre rossi pre-print (chiusi con codice, `test_red_freeze.py`)

1. Costo scrypt etichettato: ~44 ms/tentativo a regime; 13 cifre
   enumerabili (1 GPU ~3,2 anni, 100 GPU ~12 giorni — bandwidth-bound),
   19 cifre fuori portata. La difesa è l'entropia, non il per-core.
2. Codice canonico 19 cifre + `TimedCommitment` con finestra T;
   v0.06: `scrypt_hex` offuscata (blinding 128 bit), distrutta a
   `expire()` — dopo, la property solleva `UseAfterDestroyError`.
3. `SecretRegion` con memset in `__exit__` sempre; la pipeline usa il
   manager, `expose_mutable` resta API a basso livello documentata.

## Misura Docker L2 (onesta)

Linux 6.6 WSL2, Python 3.11.17: hygiene verde, lock ok; canary 19 cifre:
baseline raw 2 regioni → dopo decode 4 → dopo wipe+del+gc **ancora 4**.
utf16/hex a 1, base64 1→2, int-hex 1→2. Conclusione: L2 "ridotto e
misurato", mai garantito. Su Windows (/proc assente, hygiene rossa)
L2 correttamente **non affermato**.

## Cosa NON è garantito

- Niente R=0 in RAM col flusso reale (copie immutabili fuori controllo).
- Niente protezione dallo swap oltre la regione mlockata dichiarata.
- Niente L3 con provider remoto (vedere ARCHITETTURA).
- `del`/`drop` non cancellano: solo wipe + destroy contano.
