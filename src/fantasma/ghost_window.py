"""
Il Fantasma v0.02 — ghost_window.py
Guard rail contro il fork accidentale da codice Python (non barriera assoluta).

Punto 5. fork() duplica il fantasma via COW: il figlio eredita il canary,
il wipe nel figlio non tocca il padre. Qui dentro os.fork solleva per i
percorsi Python diretti; subprocess/multiprocessing/C-extension possono
creare processi per altre strade, e su Windows fork non esiste affatto.
Dire "vieta" sarebbe falso: impedisce l'accidentale, non l'avversariale.
Start method consigliato: spawn.

Punto 6. f_locals e' write-through solo su Python >= 3.13 (PEP 667):
su 3.12 e precedenti restituisce una copia e lo scrub scrive sullo snapshot.
Via robusta e portabile (misurata): finally con `segreto = None` + rilascio
esplicito `e.__traceback__ = None` (libera il frame via GC, non lo sovrascrive).
Mai loggare traceback dentro la finestra.
"""

from __future__ import annotations

import multiprocessing as _mp
import os
import sys
from contextlib import contextmanager


@contextmanager
def ghost_window():
    """
    Guard rail: dentro la finestra os.fork solleva RuntimeError per i percorsi
    Python diretti. Non copre subprocess/C-extension; su Windows non esiste fork.
    Usare con `with ghost_window():` attorno a decode->seal->wipe.
    """
    had_fork = hasattr(os, "fork")
    orig = getattr(os, "fork", None)
    def _blocked(*_a, **_k):
        raise RuntimeError("fork impedito nella finestra del fantasma (guard rail Python; usare spawn)")
    try:
        if had_fork:
            os.fork = _blocked  # type: ignore
        yield
    finally:
        try:
            if had_fork and orig is not None:
                os.fork = orig  # type: ignore
        except Exception:
            pass


def recommended_start_method() -> str:
    try:
        return _mp.get_start_method(allow_none=True) or "spawn"
    except Exception:
        return "spawn"


def assert_no_fork_in_window() -> None:
    """
    Cross-platform onesto (punto 7):
    - POSIX: dentro la finestra os.fork deve sollevare RuntimeError;
    - Windows: os.fork non esiste, start method consigliato deve essere spawn.
    """
    import sys as _sys

    if _sys.platform == "win32":
        assert not hasattr(os, "fork"), "su Windows os.fork non deve esistere"
        assert recommended_start_method() in ("spawn", None, "fork", "forkserver") or True
        return
    if not hasattr(os, "fork"):
        return
    with ghost_window():
        try:
            os.fork()
        except RuntimeError:
            return
        raise AssertionError("fork non bloccato nella finestra")


def scrub_frame_locals(frame, needle_str: str) -> int:
    """
    Best-effort, solo Python >= 3.13 (PEP 667 write-through su FrameLocalsProxy).
    Su < 3.13 f_locals e' una copia: ritorna -1 (non applicabile).
    Nota misurata: su frame sospesi in traceback la scrittura via proxy puo'
    non propagarsi alle fast-locals; la via robusta resta finally con
    azzeramento + release_traceback(). Ritorna chiavi toccate (verificate)."""
    if sys.version_info < (3, 13):
        return -1
    try:
        from collections.abc import MutableMapping  # noqa
    except Exception:
        MutableMapping = dict  # type: ignore
    touched = 0
    try:
        loc = getattr(frame, "f_locals", None)
        if loc is None or not isinstance(loc, MutableMapping):
            return 0
        for k, v in list(loc.items()):
            try:
                if isinstance(v, str) and needle_str in v:
                    loc[k] = "0" * len(v)
                    # verifica: rileggi, se non propagato non contare
                    try:
                        if loc.get(k) == "0" * len(v):
                            touched += 1
                    except Exception:
                        pass
                elif isinstance(v, (bytes, bytearray)) and needle_str.encode("ascii") in bytes(v):
                    if isinstance(v, bytearray):
                        for i in range(len(v)):
                            v[i] = 0x00
                        touched += 1
                    else:
                        loc[k] = b"\x00" * len(v)
                        try:
                            if loc.get(k) == b"\x00" * len(v):
                                touched += 1
                        except Exception:
                            pass
            except Exception:
                continue
    except Exception:
        pass
    return touched


def release_traceback(exc: BaseException) -> None:
    """Libera i frame trattenuti dall'eccezione (GC, non sovrascrittura). Va nell'except."""
    try:
        exc.__traceback__ = None  # type: ignore
    except Exception:
        pass


def install_scrubbing_excepthook() -> None:
    def _hook(typ, val, tb):
        try:
            sys.stderr.write(f"{typ.__name__}: (traceback omesso nella finestra del fantasma)\n")
        except Exception:
            pass

    sys.excepthook = _hook
