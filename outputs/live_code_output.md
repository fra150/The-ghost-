# OUTPUT LIVE FANTASMA

## Specifica della funzione per il totale del carrello

**Obiettivo:** definire una funzione Python, pronta da implementare e testare, che calcoli il totale di un carrello applicando uno sconto percentuale, con soldi rappresentati come `Decimal`, validazione separata dal calcolo e test automatici eseguibili.

**Firma richiesta (esempio):**
```python
def calcola_totale_carrello(righe, sconto_percentuale=Decimal("0")) -> Decimal:
    ...
```

**Requisiti vincolanti:**

1. **Nessun default mutabile condiviso**
   - Non usare parametri con default come `[]`, `{}`, `set()`.
   - Eventuali default devono essere immutabili (es. `Decimal("0")`, `None`) oppure il parametro è obbligatorio.
   - Se serve una collezione interna, crearla dentro la funzione.

2. **Nessun accesso rischioso agli elementi**
   - Non usare indici fissi tipo `riga[0]`, `riga[1]` senza controllo.
   - Iterare direttamente sulla sequenza.
   - Accedere a campi tramite chiavi/attributi solo dopo validazione, con messaggi di errore chiari.
   - Non deve mai verificarsi `IndexError`.

3. **Carrello vuoto = errore esplicito**
   - Se il carrello è vuoto, sollevare `ValueError("Il carrello è vuoto")` prima di qualsiasi divisione o calcolo.
   - Nessuna divisione per zero.

4. **Validazione sconto**
   - Lo sconto percentuale deve essere compreso tra `0` e `100` inclusi.
   - Se fuori intervallo, sollevare `ValueError` con messaggio chiaro.
   - Convertire a `Decimal` in modo sicuro, preferendo `Decimal(str(valore))` per evitare errori da `float`.

5. **Tipo decimale per gli importi**
   - Prezzi, quantità monetarie, totali e sconti usano `Decimal`.
   - Arrotondamento finale a 2 decimali con `quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)`.

6. **Separazione tra validazione e calcolo**
   - Creare una o più funzioni di validazione, ad esempio:
     - `valida_carrello(righe)`
     - `valida_sconto(sconto_percentuale)`
     - `normalizza_riga(riga)`
   - La funzione principale `calcola_totale_carrello` richiama la validazione, poi esegue solo il calcolo.
   - Il calcolo non deve contenere controlli duplicati o nascosti.

7. **Verifiche automatiche eseguibili**
   - Includere test con `assert` direttamente eseguibili.
   - I test devono coprire almeno:
     - carrello vuoto → `ValueError`
     - sconto negativo o > 100 → `ValueError`
     - quantità non positiva → `ValueError`
     - prezzo negativo → `ValueError`
     - calcolo corretto con `Decimal`
     - assenza di `IndexError` con strutture diverse (es. dizionari, tuple)
     - assenza di default mutabili.
   - I test possono essere in `if __name__ == "__main__":` o in funzioni `test_*`.

8. **Formato di consegna**
   - Restituire uno o più blocchi Python completi, pronti da salvare in file.
   - Prima del codice, scrivere **3 righe** che spiegano le scelte progettuali principali.
   - Il codice deve essere eseguibile senza dipendenze esterne oltre alla libreria standard.

**Criteri di accettazione:**
- La funzione non usa default mutabili.
- Non genera mai `IndexError`.
- Solleva `ValueError` chiaro se il carrello è vuoto.
- Valida lo sconto tra 0 e 100.
- Usa `Decimal` per tutti gli importi.
- Separa validazione e calcolo.
- Include test `assert` eseguibili e significativi.