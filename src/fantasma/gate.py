"""
Gate interno — decide se attivare il Fantasma.
Punto 2 del meccanismo: "Un gate interno decide se attivare il Fantasma."

Il gate e' esplicito e configurabile proprio per rendere visibile
il paradosso etico (punto 6 della concept note): chi progetta il gate
decide quando il modello ragiona in privato. Qui lo dichiariamo,
non lo nascondiamo.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GateDecision:
    active: bool
    score: float
    reason: str


class HeuristicGate:
    """
    Gate euristico semplice e ispezionabile.

    Si attiva quando l'input sembra richiedere ragionamento:
    - lunghezza oltre soglia
    - presenza di parole-segnale (perche', come, decidi, complesso, ecc.)
    - punteggio complessita' (n. parole interrogative, subordinate, ecc.)
    """

    def __init__(
        self,
        min_chars: int = 40,
        threshold: float = 0.5,
        keywords: list[str] | None = None,
    ) -> None:
        self.min_chars = min_chars
        self.threshold = threshold
        self.keywords = keywords or [
            "perch",
            "come",
            "perchè",
            "perché",
            "decidi",
            "decisione",
            "complesso",
            "complessa",
            "spiega",
            "ragiona",
            "dilemma",
            "paradosso",
            "confronta",
            "valuta",
            "strategia",
            "progetta",
        ]

    def score(self, user_input: str) -> tuple[float, list[str]]:
        text = user_input or ""
        lowered = text.lower()
        motivi: list[str] = []
        punti = 0.0

        # 1. lunghezza
        if len(text.strip()) >= self.min_chars:
            punti += 0.35
            motivi.append(f"lunghezza>={self.min_chars}")

        # 2. keywords
        hits = [k for k in self.keywords if k in lowered]
        if hits:
            punti += min(0.4, 0.15 + 0.1 * len(hits))
            motivi.append(f"keywords:{','.join(hits[:3])}")

        # 3. complessita' sintattica grezza
        markers = ["?", " ma ", " se ", " perché ", " perche' ", " tuttavia ", " invece "]
        m_hits = sum(1 for m in markers if m in lowered)
        if m_hits >= 1:
            punti += min(0.35, 0.12 * m_hits)
            motivi.append(f"marcatori_complessita:{m_hits}")

        # 4. multi-frase
        frasi = [f for f in text.replace("?", ".").replace("!", ".").split(".") if f.strip()]
        if len(frasi) >= 2:
            punti += 0.1
            motivi.append(f"multifrase:{len(frasi)}")

        return min(1.0, punti), motivi

    def should_activate(self, user_input: str) -> GateDecision:
        punteggio, motivi = self.score(user_input or "")
        attiva = punteggio >= self.threshold
        ragione = (
            f"ATTIVO score={punteggio:.2f} motivi=[{';'.join(motivi)}]"
            if attiva
            else f"standby score={punteggio:.2f} motivi=[{';'.join(motivi)}]"
        )
        return GateDecision(active=attiva, score=punteggio, reason=ragione)
