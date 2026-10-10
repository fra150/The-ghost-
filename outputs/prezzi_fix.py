#!/usr/bin/env python3
"""
OUTPUT LIVE FANTASMA - Totale carrello con sconto percentuale.

Regole:
- Soldi e sconti rappresentati come Decimal.
- Validazione separata dal calcolo.
- Nessun default mutabile, nessun accesso indicizzato non controllato.
- Carrello vuoto -> ValueError("Il carrello è vuoto").
"""

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import inspect

CENT = Decimal("0.01")
ZERO = Decimal("0")
CENTO = Decimal("100")


# ---------------------------------------------------------------------------
# Utilities di conversione
# ---------------------------------------------------------------------------

def _a_decimal(valore, nome_campo):
    """Converte un valore in Decimal in modo sicuro.

    Preferisce Decimal(str(valore)) per non introdurre errori binari da float.
    Rifiuta bool, tipi non numerici, NaN e Infinity.
    """
    if isinstance(valore, bool):
        raise ValueError(f"{nome_campo} non può essere un booleano: {valore!r}")

    if isinstance(valore, Decimal):
        decimale = valore
    elif isinstance(valore, (int, float, str)):
        try:
            decimale = Decimal(str(valore))
        except (InvalidOperation, ValueError, ArithmeticError) as exc:
            raise ValueError(
                f"{nome_campo} non convertibile in Decimal: {valore!r}"
            ) from exc
    else:
        raise ValueError(
            f"{nome_campo} di tipo non supportato: {type(valore).__name__}"
        )

    if not decimale.is_finite():
        raise ValueError(f"{nome_campo} deve essere un numero finito: {valore!r}")

    return decimale


# ---------------------------------------------------------------------------
# Validazione
# ---------------------------------------------------------------------------

def normalizza_riga(riga):
    """Trasforma una riga in una coppia (prezzo, quantita) di Decimal validati.

    Formati accettati:
      - Mapping con chiavi 'prezzo' e 'quantita'
      - sequenza (tuple/list) di esattamente 2 elementi (prezzo, quantita)

    Solleva sempre ValueError, mai IndexError.
    """
    if isinstance(riga, Mapping):
        if "prezzo" not in riga:
            raise ValueError("La riga dizionario non contiene la chiave 'prezzo'")
        if "quantita" not in riga:
            raise ValueError("La riga dizionario non contiene la chiave 'quantita'")
        prezzo_raw = riga["prezzo"]
        quantita_raw = riga["quantita"]
    elif isinstance(riga, (tuple, list)):
        if len(riga) != 2:
            raise ValueError(
                f"La riga sequenza deve avere esattamente 2 elementi "
                f"(prezzo, quantita), trovati {len(riga)}"
            )
        prezzo_raw, quantita_raw = riga
    else:
        raise ValueError(
            f"Formato riga non supportato: {type(riga).__name__}. "
            f"Usa una tupla/lista (prezzo, quantita) o un dizionario "
            f"con chiavi 'prezzo' e 'quantita'."
        )

    prezzo = _a_decimal(prezzo_raw, "prezzo")
    quantita = _a_decimal(quantita_raw, "quantita")

    if prezzo < ZERO:
        raise ValueError(f"Il prezzo non può essere negativo: {prezzo}")
    if quantita <= ZERO:
        raise ValueError(f"La quantità deve essere positiva: {quantita}")

    return prezzo, quantita


def valida_carrello(righe):
    """Valida e normalizza l'intero carrello.

    Ritorna una lista di tuple (prezzo, quantita) in Decimal già validati.
    Solleva ValueError("Il carrello è vuoto") se non c'è alcuna riga.
    """
    if righe is None:
        raise ValueError("Il carrello è vuoto")

    try:
        iteratore = iter(righe)
    except TypeError as exc:
        raise ValueError(
            "Le righe del carrello devono essere una sequenza iterabile"
        ) from exc

    righe_normalizzate = []
    for riga in iteratore:
        righe_normalizzate.append(normalizza_riga(riga))

    if not righe_normalizzate:
        raise ValueError("Il carrello è vuoto")

    return righe_normalizzate


def valida_sconto(sconto_percentuale):
    """Valida lo sconto percentuale e lo restituisce come Decimal in [0, 100]."""
    sconto = _a_decimal(sconto_percentuale, "sconto_percentuale")
    if sconto < ZERO or sconto > CENTO:
        raise ValueError(
            f"Lo sconto percentuale deve essere compreso tra 0 e 100 inclusi, "
            f"ricevuto: {sconto}"
        )
    return sconto


# ---------------------------------------------------------------------------
# Calcolo
# ---------------------------------------------------------------------------

def calcola_totale_carrello(righe, sconto_percentuale=Decimal("0")) -> Decimal:
    """Calcola il totale del carrello applicando uno sconto percentuale.

    Validazione delegata a valida_carrello/valida_sconto.
    Arrotondamento finale a 2 decimali con ROUND_HALF_UP.
    """
    righe_normalizzate = valida_carrello(righe)
    sconto = valida_sconto(sconto_percentuale)

    totale_lordo = ZERO
    for prezzo, quantita in righe_normalizzate:
        totale_lordo += prezzo * quantita

    totale_scontato = totale_lordo * (CENTO - sconto) / CENTO
    return totale_scontato.quantize(CENT, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Helper per i test
# ---------------------------------------------------------------------------

def _atteso_value_error(fn, *args, **kwargs):
    """Esegue fn e pretende un ValueError; ritorna il messaggio."""
    try:
        fn(*args, **kwargs)
    except ValueError as exc:
        return str(exc)
    except IndexError as exc:  # pragma: no cover - fallimento esplicito
        raise AssertionError(
            f"Ricevuto IndexError invece di ValueError: {exc}"
        ) from exc
    except Exception as exc:  # pragma: no cover - fallimento esplicito
        raise AssertionError(
            f"Atteso ValueError, ricevuto {type(exc).__name__}: {exc}"
        ) from exc
    raise AssertionError(
        "Atteso ValueError, ma nessuna eccezione è stata sollevata"
    )


# ---------------------------------------------------------------------------
# Test automatici
# ---------------------------------------------------------------------------

def test_carrello_vuoto():
    for contenitore in ([], (), set(), iter([]), None):
        msg = _atteso_value_error(calcola_totale_carrello, contenitore)
        assert "vuoto" in msg.lower(), f"Messaggio inatteso: {msg!r}"


def test_sconto_fuori_intervallo():
    righe = [(Decimal("10"), 1)]
    for sconto in (Decimal("-0.01"), Decimal("-1"), -5, "-10", Decimal("100.01"), 150, "101"):
        msg = _atteso_value_error(calcola_totale_carrello, righe, sconto)
        assert "sconto" in msg.lower(), f"Messaggio inatteso: {msg!r}"

    # Estremi validi inclusi
    assert calcola_totale_carrello(righe, Decimal("0")) == Decimal("10.00")
    assert calcola_totale_carrello(righe, Decimal("100")) == Decimal("0.00")


def test_quantita_non_positiva():
    _atteso_value_error(calcola_totale_carrello, [(Decimal("10"), 0)])
    _atteso_value_error(calcola_totale_carrello, [(Decimal("10"), -1)])
    _atteso_value_error(calcola_totale_carrello, [(Decimal("10"), Decimal("0.00"))])
    _atteso_value_error(
        calcola_totale_carrello, [{"prezzo": "10", "quantita": "0"}]
    )


def test_prezzo_negativo():
    _atteso_value_error(calcola_totale_carrello, [(Decimal("-0.01"), 1)])
    _atteso_value_error(calcola_totale_carrello, [{"prezzo": "-1", "quantita": 2}])
    # Prezzo zero è ammesso (non negativo)
    assert calcola_totale_carrello([(Decimal("0"), 5)]) == Decimal("0.00")


def test_calcolo_corretto():
    righe = [(Decimal("10.00"), 2), (Decimal("5.50"), 1)]
    totale = calcola_totale_carrello(righe)
    assert totale == Decimal("25.50"), totale
    assert isinstance(totale, Decimal)
    assert calcola_totale_carrello(righe, Decimal("10")) == Decimal("22.95")
    assert calcola_totale_carrello(righe, "10") == Decimal("22.95")
    assert calcola_totale_carrello(righe, 10) == Decimal("22.95")
    # Carrello interamente scontato
    assert calcola_totale_carrello(righe, Decimal("100")) == Decimal("0.00")


def test_arrotondamento_half_up():
    righe = [(Decimal("10.00"), 1)]
    # 10 * 66.67 / 100 = 6.667 -> 6.67 con HALF_UP
    assert calcola_totale_carrello(righe, Decimal("33.33")) == Decimal("6.67")
    # 2.345 -> 2.35 con HALF_UP
    assert calcola_totale_carrello([(Decimal("2.345"), 1)]) == Decimal("2.35")
    # 2.344 -> 2.34
    assert calcola_totale_carrello([(Decimal("2.344"), 1)]) == Decimal("2.34")


def test_strutture_diverse():
    atteso = Decimal("20.00")

    # lista di tuple
    assert calcola_totale_carrello([(Decimal("10"), 2)]) == atteso
    # lista di liste
    assert calcola_totale_carrello([[Decimal("10"), 2]]) == atteso
    # lista di dizionari
    assert calcola_totale_carrello(
        [{"prezzo": Decimal("10"), "quantita": Decimal("2")}]
    ) == atteso
    # tupla di tuple
    assert calcola_totale_carrello(((Decimal("10"), 2),)) == atteso
    # tupla di dizionari
    assert calcola_totale_carrello(({"prezzo": "10", "quantita": "2"},)) == atteso
    # generatore di righe
    assert calcola_totale_carrello(
        (r for r in [(Decimal("10"), 2)])
    ) == atteso
    # mista
    misto = [
        (Decimal("10"), 1),
        {"prezzo": "5.00", "quantita": 2},
    ]
    assert calcola_totale_carrello(misto) == Decimal("20.00")
    # chiavi extra sono ignorate
    assert calcola_totale_carrello(
        [{"prezzo": "10", "quantita": 2, "descrizione": "x"}]
    ) == atteso


def test_nessun_index_error():
    casi = [
        [],
        [[]],
        [()],
        [(Decimal("10"),)],
        [(Decimal("10"), 2, 3)],
        [{}],
        [{"prezzo": "10"}],
        [{"quantita": 2}],
        ["stringa"],
        [None],
        [123],
        [object()],
        [(True, 1)],
        [(Decimal("1"), True)],
    ]
    for caso in casi:
        try:
            calcola_totale_carrello(caso)
        except IndexError as exc:
            raise AssertionError(
                f"IndexError inatteso per il caso {caso!r}"
            ) from exc
        except ValueError:
            pass  # atteso: validazione corretta
        else:
            raise AssertionError(
                f"Atteso ValueError per il caso {caso!r}, nessuna eccezione sollevata"
            )

    # 'righe' non iterabile -> ValueError, non TypeError
    msg = _atteso_value_error(calcola_totale_carrello, 42)
    assert "iterabile" in msg.lower(), msg

    # chiavi extra tollerate (forward-compat): nessun IndexError, calcolo ok
    assert calcola_totale_carrello(
        [{"prezzo": "10", "quantita": "2", "extra": 1}]
    ) == Decimal("20.00")


def test_conversione_sicura():
    # float 0.1 -> Decimal("0.1") tramite str(), nessun errore binario
    assert calcola_totale_carrello([(0.1, 1)]) == Decimal("0.10")
    assert calcola_totale_carrello([("0.1", 1)]) == Decimal("0.10")
    assert calcola_totale_carrello([(1, 1)]) == Decimal("1.00")

    # Valori non convertibili
    _atteso_value_error(calcola_totale_carrello, [("abc", 1)])
    _atteso_value_error(calcola_totale_carrello, [(Decimal("1"), "xyz")])
    _atteso_value_error(calcola_totale_carrello, [("", 1)])
    # NaN / Infinity
    _atteso_value_error(calcola_totale_carrello, [("NaN", 1)])
    _atteso_value_error(calcola_totale_carrello, [("Infinity", 1)])
    _atteso_value_error(calcola_totale_carrello, [("-Infinity", 1)])
    # Booleani
    _atteso_value_error(calcola_totale_carrello, [(True, 1)])
    _atteso_value_error(calcola_totale_carrello, [(Decimal("1"), False)])


def test_default_immutabili():
    firma = inspect.signature(calcola_totale_carrello)

    for nome, parametro in firma.parameters.items():
        if parametro.default is inspect.Parameter.empty:
            continue
        default = parametro.default
        assert not isinstance(default, (list, dict, set, bytearray)), (
            f"Default mutabile non ammesso per il parametro {nome!r}"
        )

    # Firma coerente con la specifica
    assert firma.parameters["righe"].default is inspect.Parameter.empty
    assert firma.parameters["sconto_percentuale"].default == Decimal("0")

    # Le firme dei validatori non hanno default mutabili
    for funzione in (valida_carrello, valida_sconto, normalizza_riga):
        for nome, parametro in inspect.signature(funzione).parameters.items():
            if parametro.default is inspect.Parameter.empty:
                continue
            assert not isinstance(
                parametro.default, (list, dict, set, bytearray)
            ), f"Default mutabile in {funzione.__name__}.{nome}"


def test_nessuno_stato_condiviso():
    # Chiamate successive su carrelli diversi non si influenzano
    risultati = [
        calcola_totale_carrello([(Decimal("10"), 1)]),
        calcola_totale_carrello([(Decimal("10"), 1)]),
        calcola_totale_carrello([(Decimal("10"), 1)]),
    ]
    assert risultati == [Decimal("10.00")] * 3

    # Modificare la lista sorgente dopo la chiamata non altera il risultato
    righe = [(Decimal("10"), 1)]
    primo = calcola_totale_carrello(righe)
    righe.append((Decimal("5"), 1))
    assert primo == Decimal("10.00")


def test_input_originale_non_modificato():
    righe = [(Decimal("10"), 2), {"prezzo": "5", "quantita": 1}]
    copia = list(righe)
    calcola_totale_carrello(righe, Decimal("10"))
    assert righe == copia


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_carrello_vuoto()
    test_sconto_fuori_intervallo()
    test_quantita_non_positiva()
    test_prezzo_negativo()
    test_calcolo_corretto()
    test_arrotondamento_half_up()
    test_strutture_diverse()
    test_nessun_index_error()
    test_conversione_sicura()
    test_default_immutabili()
    test_nessuno_stato_condiviso()
    test_input_originale_non_modificato()
    print("Tutti i test sono passati.")
