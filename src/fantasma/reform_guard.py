"""
Il Fantasma v0.04 — reform_guard.py (P0 scientifico).

Gate di validazione semantica tra Call-1 e Call-2.
Problema: Call-1 (FANTASMA-INTERPRETA) a volte produce direttamente
`#### N` invece di una direttiva verbale astratta (ID36 v0.03).
La risposta trafila nella riformulazione e scavalca il sigillo.

Regola v0.04 (allowlist, non blocklist cieca):
- i numeri gia' presenti nella domanda originale sono LEGITTIMI
  (la riformulazione puo' ripeterli);
- sono VIETATI: il formato risposta `#### N` e i numeri NUOVI
  (non presenti nella domanda), in particolare quelli lunghi (>=4 cifre).
- la densita' numerica da sola non boccia: se la riformulazione
  ripete solo numeri vecchi (domanda densa), passa.

Normalizzazione (anti-evasione banale):
- "160.000" / "160,000" / "160 000" / "160'000" -> "160000";
- "160 mila" / "2 milioni" / "3,5k" -> valore espanso;
- cifre in lettere italiane comuni ("dodici", "trenta", "cento", ...)
  mappate a canonico. Copertura dichiarata parziale: casi compositi
  complessi ("centosessantamila" attaccato) possono sfuggire ed e'
  documentato come limite noto, non come garanzia.

Uso nelle pipeline:
    guard = ReformulationGuard()
    try:
        clean = guard.validate(interpretation, user_input)
    except LeakageDetectedError:
        # retry Call-1 (max 2) poi fallback pulito, MAI passare a Call-2
        ...

Reporting (anti-bias da fallback):
- validate_with_report() ritorna {ok, reason, new_numbers, ...};
- l'harness DEVE riportare tasso di intervento + accuratezza separata
  su {passate pulite / fallback / totale}, mai mescolate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


class LeakageDetectedError(Exception):
    """Riformulazione respinta: trafilamento di risposta o numeri vietati."""


# -- prompt rigido Call-1 (v0.04) -------------------------------------------
# Da usare in pipeline_v02, pipeline_reformonly e bracci di ablazione.
CALL1_RIGID_TAIL = (
    "Restituisci SOLO una direttiva di riformulazione verbale astratta. "
    "Divieti assoluti: nessuna cifra arabica aggiuntiva rispetto alla domanda, "
    "nessun formato '####', nessun numero finale, nessun codice. "
    "Puoi ripetere i numeri gia' presenti nella domanda, senza aggiungerne altri."
)

FORBIDDEN_ANSWER_RE = re.compile(r"####\s*-?\d")

_DIGIT_RUN_RE = re.compile(r"\d[\d\.,\s'\u2019]*\d|\d")

_MAGNITUDE_RE = re.compile(
    r"(\d[\d\.,\s'\u2019]*)\s*(mila|mille|milioni|milione|miliardi|miliardo|k)\b",
    re.IGNORECASE,
)

_MAGNITUDE_MULT = {
    "mille": 1_000,
    "mila": 1_000,
    "k": 1_000,
    "milione": 1_000_000,
    "milioni": 1_000_000,
    "miliardo": 1_000_000_000,
    "miliardi": 1_000_000_000,
}

# Vocabolario italiano minimo (0-99 + cento/mille/milione/miliardo).
# Limite noto: composti attaccati ("centosessanta") o locuzioni lunghe
# ("duecentotrentacinquemila") non sono coperti.
_IT_WORDS: dict[str, int] = {
    "zero": 0, "uno": 1, "una": 1, "un": 1, "due": 2, "tre": 3,
    "quattro": 4, "cinque": 5, "sei": 6, "sette": 7, "otto": 8,
    "nove": 9, "dieci": 10, "undici": 11, "dodici": 12, "tredici": 13,
    "quattordici": 14, "quindici": 15, "sedici": 16, "diciassette": 17,
    "diciotto": 18, "diciannove": 19, "venti": 20, "trenta": 30,
    "quaranta": 40, "cinquanta": 50, "sessanta": 60, "settanta": 70,
    "ottanta": 80, "novanta": 90, "cento": 100, "mille": 1000,
    "mila": 1000, "milione": 1_000_000, "milioni": 1_000_000,
    "miliardo": 1_000_000_000, "miliardi": 1_000_000_000,
}

_WORD_MAGNITUDE_RE = re.compile(
    r"\b(zero|uno|una|un|due|tre|quattro|cinque|sei|sette|otto|nove|"
    r"dieci|undici|dodici|tredici|quattordici|quindici|sedici|"
    r"diciassette|diciotto|diciannove|venti|trenta|quaranta|cinquanta|"
    r"sessanta|settanta|ottanta|novanta|cento)\s+"
    r"(mila|mille|milioni|milione|miliardi|miliardo)\b",
    re.IGNORECASE,
)


def _canonical_digits(raw: str) -> str:
    """"160.000" -> "160000"; "007" -> "7"; "" -> ""."""
    t = re.sub(r"[\.,\s'\u2019]", "", raw or "")
    t = re.sub(r"\D", "", t)
    if not t:
        return ""
    t = t.lstrip("0") or "0"
    return t


def canonical_numbers_in(text: str) -> set[str]:
    """Tutti i numeri canonici presenti nel testo (digit + magnitude + parole)."""
    out: set[str] = set()
    t = text or ""
    for m in _DIGIT_RUN_RE.finditer(t):
        c = _canonical_digits(m.group(0))
        if c:
            out.add(c)
    for m in _MAGNITUDE_RE.finditer(t):
        base = _canonical_digits(m.group(1))
        mult = _MAGNITUDE_MULT.get(m.group(2).lower(), 1)
        if base:
            try:
                out.add(str(int(base) * mult))
            except ValueError:
                pass
    lowered = t.lower()
    for w, v in _IT_WORDS.items():
        if re.search(rf"\b{re.escape(w)}\b", lowered):
            out.add(str(v))
    for m in _WORD_MAGNITUDE_RE.finditer(t):
        w = m.group(1).lower()
        mult = _MAGNITUDE_MULT.get(m.group(2).lower(), 1)
        base = _IT_WORDS.get(w)
        if base is not None:
            out.add(str(int(base) * mult))
    out.discard("")
    return out


@dataclass(frozen=True)
class ReformulationGuard:
    """Gate allowlist tra Call-1 e Call-2. Vedi docstring del modulo."""

    max_digit_ratio: float = 0.08
    min_new_digits_len: int = 4
    forbidden_answer: re.Pattern = field(default=FORBIDDEN_ANSWER_RE)

    def validate(self, reform: str, user_input: str) -> str:
        text = (reform or "").strip()
        if not text:
            raise LeakageDetectedError("riformulazione vuota")
        if self.forbidden_answer.search(text):
            raise LeakageDetectedError("formato risposta '#### N' nella riformulazione")
        old = canonical_numbers_in(user_input or "")
        new_all = canonical_numbers_in(text) - set(old)
        # Numeri nuovi lunghi (>= min_new_digits_len cifre, zeri iniziali ignorati)
        sensitive = [n for n in new_all if len(n.lstrip("0") or "0") >= self.min_new_digits_len]
        if sensitive:
            raise LeakageDetectedError(f"numeri nuovi non autorizzati: {sorted(sensitive)[:5]}")
        digits = sum(c.isdigit() for c in text)
        ratio = digits / max(len(text), 1)
        if ratio > self.max_digit_ratio and new_all:
            raise LeakageDetectedError(
                f"densita' numerica anomala ({ratio:.2f}) con numeri nuovi: {sorted(new_all)[:5]}"
            )
        return text

    def validate_with_report(self, reform: str, user_input: str) -> dict:
        text = (reform or "").strip()
        old = canonical_numbers_in(user_input or "")
        new_all = sorted(canonical_numbers_in(text) - set(old))
        digits = sum(c.isdigit() for c in text)
        ratio = round(digits / max(len(text), 1), 4)
        try:
            clean = self.validate(reform, user_input)
            return {
                "ok": True, "reason": "pass",
                "new_numbers": new_all, "digit_ratio": ratio,
                "clean": clean,
            }
        except LeakageDetectedError as exc:
            return {
                "ok": False, "reason": str(exc),
                "new_numbers": new_all, "digit_ratio": ratio,
                "clean": None,
            }


def build_call1_prompt(code_display: str, question: str, marker: str = "FANTASMA-INTERPRETA") -> str:
    """Prompt Call-1 rigido v0.04. Il codice e' mostrato, mai generato qui."""
    return (
        f"{marker}\n"
        f"Sei la stessa intelligenza che ha generato questo pensiero privato.\n"
        f"Codice fantasma: {code_display}\n"
        f"Richiesta originale: {(question or '').strip()}\n"
        f"{CALL1_RIGID_TAIL}"
    )
