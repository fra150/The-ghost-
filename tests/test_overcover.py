"""Test di riferimento over-cover (documento di correzione, 51 test).

Misura associata (citata nel paper v0.05 corretta, §6):
- falsi positivi del criterio di copertura su numeri nudi: un 11-cifre
  supera la P.IVA nel 10,15% dei casi, un 16-cifre supera Luhn nel 10,0%,
  un 13-cifre nel 9,8% (20 000 numeri casuali, seed 20261010);
- sostituzioni strict di `find_cover_spans` sui 50 problemi GSM8K: 0.

I conteggi esatti del protocollo (2030 / 1956 / 1999) sono riprodotti da
`fantasma.overcover_ref`; la resa in percentuale del paper (due decimali per
la P.IVA, un decimale per Luhn) e' verificata col riporto standard (mezza
unita' in su) su aritmetica decimale esatta, non su float.
"""

import json
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fantasma.overcover_ref import (  # noqa: E402
    EXPECTED_COUNTS,
    LENGTHS,
    N_DRAWS,
    SEED,
    count_false_positives,
    count_strict_spans,
    reference_rates,
)
from fantasma.pii_cover import (  # noqa: E402
    cf_ok,
    cover_text,
    find_cover_spans,
    iban_ok,
    luhn_ok,
    piva_ok,
)

CARDS_OK = [
    "4111111111111111",
    "4012888888881881",
    "5555555555554444",
    "6011111111111117",
    "378282246310005",
]
PIVA_PREFIXES = ["1234567890", "0000000000", "1111111111", "0764352056", "9999999999"]
IBAN_OK = "IT60X0542811101000000123456"
IBAN_BAD = "IT60X0542811101000000123457"
CF_OK = "RSSMRA85M01H501Q"
CORPUS = ROOT / "outputs" / "benchmark" / "gsm8k_50_4arm_v03.jsonl"

QUANTITA_NUDE = ["2880000", "54", "160000", "907153", "3.14159", "20"]

MATH_TEXTS = [
    "Janet's ducks lay 16 eggs per day. She eats three for breakfast and sells the rest at $2 each.",
    "A robe takes 2 bolts of blue fiber and half that much white fiber.",
    "Natalia sold clips to 48 friends in April, and half as many in May.",
    "Weng earns $12 an hour for babysitting. Yesterday she babysat for 50 minutes.",
    "Carlos plants a lemon tree for $90; 7 lemons per year at $1.5 each; costs $3 per year.",
    "Betty is saving $5 a week; her parents pay $0.5 per chore and she does 100 chores.",
]


def _piva_from_prefix(prefix10: str) -> str:
    """Costruisce una P.IVA valida dalla prima parte (stesso algoritmo del modulo)."""
    s = 0
    for i in range(10):
        d = int(prefix10[i])
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        s += d
    return prefix10 + str((10 - s % 10) % 10)


def _pct_display(hits: int, draws: int, dp: int) -> str:
    """Resa percentuale con riporto esatto (come nel paper, mezza unita' in su)."""
    q = (Decimal(100 * hits) / Decimal(draws)).quantize(
        Decimal(1).scaleb(-dp), rounding=ROUND_HALF_UP
    )
    return f"{q}%"


def _corpus_texts() -> list[str]:
    texts = []
    with CORPUS.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if isinstance(row.get("question_full"), str):
                texts.append(row["question_full"])
    return texts


@pytest.fixture(scope="module")
def rates():
    return reference_rates()


# -- 1-4: checksum di base sui valori reali del dominio -----------------------

@pytest.mark.parametrize("card", CARDS_OK)
def test_luhn_carte_valide(card):
    assert luhn_ok(card)


@pytest.mark.parametrize("card", CARDS_OK)
def test_luhn_carta_mutata_invalida(card):
    mutata = card[:-1] + str((int(card[-1]) + 1) % 10)
    assert not luhn_ok(mutata)


@pytest.mark.parametrize("prefix", PIVA_PREFIXES)
def test_piva_valida(prefix):
    assert piva_ok(_piva_from_prefix(prefix))


@pytest.mark.parametrize("prefix", PIVA_PREFIXES)
def test_piva_mutata_invalida(prefix):
    valida = _piva_from_prefix(prefix)
    mutata = valida[:-1] + str((int(valida[-1]) + 1) % 10)
    assert not piva_ok(mutata)


# -- 5-6: IBAN e codice fiscale ----------------------------------------------

def test_iban_valido():
    assert iban_ok(IBAN_OK)


def test_iban_cifra_mutata_invalida():
    assert not iban_ok(IBAN_BAD)


def test_iban_accetta_minuscole():
    assert iban_ok(IBAN_OK.lower())


def test_cf_valido():
    assert cf_ok(CF_OK)


def test_cf_mutato_o_illecito_invalido():
    assert not cf_ok("RSSMRA85M01H501A")
    assert not cf_ok("RSSMRA85M01H501!")


# -- 7-8: conteggi esatti del protocollo e resa nel paper ---------------------

@pytest.mark.parametrize("length", LENGTHS)
def test_conteggio_falsi_positivi_esatto(length):
    assert count_false_positives(length) == EXPECTED_COUNTS[length]


@pytest.mark.parametrize(
    ("length", "dp", "atteso"),
    [(11, 2, "10.15%"), (13, 1, "9.8%"), (16, 1, "10.0%")],
)
def test_percentuale_come_nel_paper(rates, length, dp, atteso):
    r = rates[length]
    assert _pct_display(r["hits"], r["draws"], dp) == atteso


# -- 9-12: proprieta' del riferimento ----------------------------------------

def test_riferimento_deterministico():
    assert count_false_positives(11) == count_false_positives(11)


def test_reference_rates_struttura(rates):
    assert set(rates) == set(LENGTHS)
    for n in LENGTHS:
        assert set(rates[n]) == {"hits", "draws", "pct"}
        assert rates[n]["draws"] == N_DRAWS


def test_reference_rates_pct_coerente(rates):
    for n in LENGTHS:
        r = rates[n]
        assert r["pct"] == pytest.approx(100.0 * r["hits"] / r["draws"])


def test_reference_rates_json_serializzabile(rates):
    blob = json.dumps({str(k): v for k, v in rates.items()})
    assert json.loads(blob)["11"]["hits"] == EXPECTED_COUNTS[11]


# -- 13-14: sostituzioni strict su testi matematici e su identificatori -------

def test_strict_zero_su_testi_matematici():
    assert count_strict_spans(MATH_TEXTS)["total"] == 0


def test_strict_conta_identificatori_reali():
    testo = "CF RSSMRA85M01H501Q, P.IVA 12345678903 e carta 4111 1111 1111 1111."
    rep = count_strict_spans([testo])
    assert rep["total"] == 3
    assert set(rep["by_tag"]) == {"CF", "PIVA", "CARD"}


@pytest.mark.parametrize("nuda", QUANTITA_NUDE)
def test_quantita_nude_senza_span(nuda):
    assert find_cover_spans(nuda) == []


@pytest.mark.skipif(not CORPUS.exists(), reason="corpus benchmark locale assente")
def test_corpus_benchmark_zero_sostituzioni():
    rep = count_strict_spans(_corpus_texts())
    assert rep["texts"] == 50
    assert rep["total"] == 0


# -- 17-20: bordi dei validatori ---------------------------------------------

@pytest.mark.parametrize("length", [12, 20])
def test_luhn_lunghezze_fuori_range(length):
    assert not luhn_ok("1" * length)


def test_piva_rifiuta_non_cifre():
    assert not piva_ok("1234567890A")
    assert not piva_ok("123456789 0")
    assert not piva_ok("")


def test_cf_rifiuta_caratteri_illeciti():
    assert not cf_ok("RSSMRA85M01H501!")
    assert not cf_ok("RSSMRA85M01H501")
    assert not cf_ok("")


# -- 21-22: span di contatto e report della cover -----------------------------

def test_span_email_e_telefono():
    testo = "Scrivi a m.rossi@studio.it oppure al +39 333 1234567 entro oggi."
    tag = {t for _s, _e, t, _v in find_cover_spans(testo)}
    assert tag == {"EMAIL", "PHONE"}


def test_report_cover_conta_i_tag():
    testo = "CF RSSMRA85M01H501Q, P.IVA 12345678903 e carta 4111 1111 1111 1111."
    rep = cover_text(testo).report
    assert rep["n_values"] == 3
    assert rep["by_tag"] == {"CF": 1, "PIVA": 1, "CARD": 1}


def test_expected_counts_allineati_ai_valori_pubblicati():
    assert EXPECTED_COUNTS == {11: 2030, 13: 1956, 16: 1999}
    assert (SEED, N_DRAWS) == (20261010, 20000)
