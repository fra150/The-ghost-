"""
Il Fantasma v0.05 — pii_cover.py (cover pre-CoT, mezzi propri + modelli open locali).

Idea: coprire gli identificatori DIRETTAMENTE nell'input, PRIMA che qualsiasi
chiamata al modello parta (pre-CoT), con placeholder stabili e reversibili in
locale. Il modello (remoto o locale) vede solo placeholder; i valori veri non
lasciano mai la macchina e vengono reinseriti nell'output finale in locale.

Strato deterministico (default, zero dipendenze, solo stdlib): rete
regex + checksum per gli identificatori strutturati italiani e
internazionali (CF, PIVA, IBAN, carte, email, telefoni). Solo i valori con
checksum VALIDO vengono coperti: le quantita' nude dei problemi di
matematica (es. 2880000, 54) restano intatte per costruzione — la cover non
deve mai rompere il benchmark.

Strato open-class (sperimentale, opt-in): nomi propri e luoghi non si
coprono con regex; serve un modello open in locale (es. via Ollama,
loopback, nessun byte alla rete) che elenca gli span, poi la copertura
e' per match esatto. Mai un modello remoto per questo passo: coprire via
cloud per proteggersi dal cloud sarebbe una contraddizione.

Placeholder: `[PII_TAG_N]` (es. `[PII_CF_1]`). Mai solo-cifre, mai `####`,
mai confondibili col codice fantasma a 19 cifre. Stabili per valore:
lo stesso valore riusato nello stesso testo ottiene lo stesso placeholder
(coerenza per il ragionamento del modello).

Il mapping e' materiale sensibile: vive in bytearray wipabili, si
distrugge con wipe() + ricevuta nel BoltRegistry (stesso catenaccio del
resto), ogni riuso dopo wipe alza UseAfterDestroyError. Le str temporanee
create per il confronto sono inevitabili in Python (stesso avviso L2 di
SecretBytes.decode_at_boundary): il wipe azzera gli store, non le copie
immutabili transitorie.

Limiti dichiarati (non garanzie):
- senza checksum non si copre: un identificatore con checksum invalido o
  formato ignoto resta in chiaro (misurato dal residual scan, non promesso);
- le classi aperte (nomi/luoghi) restano in chiaro senza lo strato open-class;
- il claim resta "ridotto e misurato", mai "garantito" con provider remoto.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# -- checksum ---------------------------------------------------------------

def luhn_ok(digits: str) -> bool:
    """Luhn su sole cifre, lunghezza 13-19."""
    if not digits.isdigit() or not 13 <= len(digits) <= 19:
        return False
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = ord(ch) - 48
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def iban_ok(value: str) -> bool:
    """mod-97 == 1 dopo rearrangement (solo caratteri ammessi)."""
    v = re.sub(r"\s+", "", value or "").upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", v):
        return False
    rearr = v[4:] + v[:4]
    num = "".join(str(ord(c) - 55) if c.isalpha() else c for c in rearr)
    return int(num) % 97 == 1


def piva_ok(digits: str) -> bool:
    """Partita IVA: 11 cifre, check decimale sull'ultima."""
    if not re.fullmatch(r"\d{11}", digits or ""):
        return False
    s = 0
    for i in range(10):
        d = ord(digits[i]) - 48
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        s += d
    return (10 - s % 10) % 10 == (ord(digits[10]) - 48)


_CF_ODD = {
    "0": 1, "1": 0, "2": 5, "3": 7, "4": 9, "5": 13, "6": 15,
    "7": 17, "8": 19, "9": 21, "A": 1, "B": 0, "C": 5, "D": 7,
    "E": 9, "F": 13, "G": 15, "H": 17, "I": 19, "J": 21, "K": 2,
    "L": 4, "M": 18, "N": 20, "O": 11, "P": 3, "Q": 6, "R": 8,
    "S": 12, "T": 14, "U": 16, "V": 10, "W": 22, "X": 25, "Y": 24,
    "Z": 23,
}


def cf_ok(code: str) -> bool:
    """Codice fiscale: 16 caratteri, cin di controllo sulle prime 15 posizioni."""
    v = (code or "").upper()
    if not re.fullmatch(r"[A-Z]{6}[A-Z0-9]{2}[A-Z][A-Z0-9]{2}[A-Z][A-Z0-9]{3}[A-Z]", v):
        return False
    total = 0
    for i, ch in enumerate(v[:15]):
        if i % 2 == 0:  # 1a, 3a, ... (dispari): tabella ODD
            total += _CF_ODD[ch]
        elif ch.isdigit():
            total += ord(ch) - 48
        else:
            total += ord(ch) - 65
    return chr(65 + total % 26) == v[15]


# -- finder -----------------------------------------------------------------

_CF_RE = re.compile(r"\b[A-Za-z]{6}[A-Za-z0-9]{2}[A-Za-z][A-Za-z0-9]{2}[A-Za-z][A-Za-z0-9]{3}[A-Za-z]\b")
_PIVA_RE = re.compile(r"\b\d{11}\b")
_IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b", re.IGNORECASE)
_CARD_RE = re.compile(r"\b(?:\d[ \-]?){13,19}\b")
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE_RE = re.compile(
    r"(?:\+39|0039)[\s./]?\d{2,4}[\s./]?\d{5,8}"
    r"|\b3\d{2}[\s./]?\d{3}[\s./]?\d{4}\b"
    r"|\b0\d{1,3}[\s./]?\d{5,8}\b"
)


def _spans_for(tag: str, pattern: re.Pattern, text: str, valid) -> list[tuple[int, int, str, str]]:
    out = []
    for m in pattern.finditer(text):
        raw = m.group(0)
        norm = re.sub(r"[\s\-]", "", raw)
        if valid(norm):
            out.append((m.start(), m.end(), tag, raw))
    return out


def find_cover_spans(text: str) -> list[tuple[int, int, str, str]]:
    """Span non sovrapposti (start, end, tag, valore) con checksum valido.

    Ordine: prima gli span piu' lunghi a parita' di start (l'IBAN vince sulle
    sotto-sequenze di cifre che Luhn coprirebbe da solo).
    """
    t = text or ""
    cands: list[tuple[int, int, str, str]] = []
    cands += _spans_for("IBAN", _IBAN_RE, t, iban_ok)
    cands += _spans_for("CF", _CF_RE, t, cf_ok)
    cands += _spans_for("PIVA", _PIVA_RE, t, piva_ok)
    cands += _spans_for("CARD", _CARD_RE, t, lambda n: luhn_ok(n))
    cands += _spans_for("EMAIL", _EMAIL_RE, t, lambda n: True)
    cands += _spans_for("PHONE", _PHONE_RE, t,
                        lambda n: sum(c.isdigit() for c in n) >= 9)
    cands.sort(key=lambda s: (s[0], -(s[1] - s[0])))
    taken: list[tuple[int, int, str, str]] = []
    last_end = -1
    for s, e, tag, raw in cands:
        if s >= last_end:
            taken.append((s, e, tag, raw))
            last_end = e
    return taken


# -- mapping ------------------------------------------------------------------

class CoverMapping:
    """placeholder -> valore (bytearray wipabile). Distruggibile come il resto.

    Stabile per valore: lo stesso valore ottiene sempre lo stesso placeholder
    dentro la stessa istanza (coerenza per il modello).
    """

    def __init__(self) -> None:
        self._to_value: dict[str, bytearray] = {}
        self._by_value: dict[str, str] = {}
        self._counters: dict[str, int] = {}
        self._destroyed = False

    def _check_live(self, what: str) -> None:
        if self._destroyed:
            from .bolt import UseAfterDestroyError as _BoltErr

            raise _BoltErr(f"Mapping cover distrutto: {what} rilevato, catenaccio chiuso.")

    def placeholder_for(self, tag: str, value: str) -> str:
        self._check_live("assegnazione placeholder")
        if value in self._by_value:
            return self._by_value[value]
        n = self._counters.get(tag, 0) + 1
        self._counters[tag] = n
        ph = f"[PII_{tag}_{n}]"
        self._to_value[ph] = bytearray(value.encode("utf-8"))
        self._by_value[value] = ph
        return ph

    def restore(self, text: str) -> str:
        """Reinserisce i valori veri (boundary verso l'utente, in locale)."""
        self._check_live("restore")
        out = text or ""
        for ph, buf in self._to_value.items():
            if ph in out:
                val = bytes(buf).decode("utf-8")
                out = out.replace(ph, val)
                del val
        return out

    def values_present_in(self, text: str) -> list[dict]:
        """Valori veri ancora leggibili nel testo (residual scan sul coperto).

        Da usare sul testo COPERTO (pre-restore): se trova qualcosa, la cover
        ha mancato uno span in input e il modello potrebbe averlo ripetuto.
        """
        self._check_live("residual scan")
        t = text or ""
        hits = []
        for ph, buf in self._to_value.items():
            val = bytes(buf).decode("utf-8")
            if val and val in t:
                # tag estratto dal placeholder "[PII_TAG_N]"
                tag = ph.strip("[]").split("_")[1] if "_" in ph else "?"
                hits.append({"placeholder": ph, "tag": tag, "len": len(val)})
            del val
        return hits

    def wipe(self) -> bool:
        """Azzera i valori e dimentica la mappa. True la prima volta."""
        if self._destroyed:
            return False
        try:
            try:
                from .hygiene import secure_wipe_buffer as _wipe

                for buf in self._to_value.values():
                    try:
                        _wipe(buf)
                    except Exception:
                        for i in range(len(buf)):
                            buf[i] = 0x00
            except Exception:
                for buf in self._to_value.values():
                    for i in range(len(buf)):
                        buf[i] = 0x00
        finally:
            self._to_value.clear()
            self._by_value.clear()
            self._destroyed = True
        return True

    @property
    def is_destroyed(self) -> bool:
        return self._destroyed

    def __len__(self) -> int:
        return 0 if self._destroyed else len(self._to_value)

    def __del__(self):  # best-effort, mai alzare
        try:
            self.wipe()
        except Exception:
            pass


@dataclass
class CoverResult:
    covered: str
    mapping: CoverMapping
    report: dict = field(default_factory=dict)


def cover_text(text: str, mapping: CoverMapping | None = None) -> CoverResult:
    """Copre gli identificatori strutturati. Invariante: nessun valore trovato
    resta nel testo coperto (verificato dai test su ogni tag)."""
    t = text or ""
    mp = mapping or CoverMapping()
    counts: dict[str, int] = {}
    # stesso valore -> stesso placeholder: indicizza per valore
    by_value: dict[str, str] = {}
    for _, _, tag, raw in find_cover_spans(t):
        if raw not in by_value:
            by_value[raw] = mp.placeholder_for(tag, raw)
    # sostituzione dalle posizioni piu' avanzate (span stabili)
    spans = sorted(find_cover_spans(t), key=lambda s: -s[0])
    out = t
    for s, e, tag, raw in spans:
        ph = by_value[raw]
        out = out[:s] + ph + out[e:]
        counts[tag] = counts.get(tag, 0) + 1
    # una sostituzione per valore distinto (stabile e contabile)
    distinct = {tag: 0 for tag in counts}
    for raw, ph in by_value.items():
        tag = ph.strip("[]").split("_")[1]
        distinct[tag] = distinct.get(tag, 0) + 1
    return CoverResult(covered=out, mapping=mp,
                       report={"spans": sum(counts.values()), "by_tag": distinct,
                               "n_values": len(by_value)})


# -- strato open-class (sperimentale, solo modelli open in locale) -------------

OPEN_CLASS_PROMPT = (
    "Elenca ESCLUSIVAMENTE i nomi propri di persona e i toponimi presenti "
    "nel testo qui sotto, uno per riga nel formato `SPAN | <testo esatto>`. "
    "Niente spiegazioni, niente virgolette, niente altro. Se non ce ne sono, "
    "restituisci una sola riga con `NESSUNO`.\nTesto:\n"
)


def cover_open_classes_with_local_model(text: str, llm_fn,
                                        mapping: CoverMapping | None = None,
                                        tag: str = "NAME") -> CoverResult:
    """Sperimentale: classi aperte via modello OPEN in locale (loopback).

    `llm_fn` e' un callable str->str (es. adapter Ollama su localhost: mai un
    modello remoto — coprire via cloud per proteggersi dal cloud non ha senso).
    Copertura per match esatto case-sensitive sui span restituiti; righe non
    trovate nel testo ignorate (niente invenzioni). Iniettabile nei test.
    """
    t = text or ""
    mp = mapping or CoverMapping()
    resp = (llm_fn(OPEN_CLASS_PROMPT + t) or "").strip()
    found: list[str] = []
    for line in resp.splitlines():
        line = line.strip()
        if not line or line == "NESSUNO":
            continue
        if "|" in line:
            _, _, span = line.partition("|")
            span = span.strip()
        else:
            span = line
        if span and span in t and span not in found:
            found.append(span)
    out = t
    counts = 0
    for span in sorted(found, key=len, reverse=True):
        ph = mp.placeholder_for(tag, span)
        out = out.replace(span, ph)
        counts += 1
    return CoverResult(covered=out, mapping=mp,
                       report={"spans": counts, "by_tag": {tag: counts},
                               "n_values": counts, "experimental": True})
