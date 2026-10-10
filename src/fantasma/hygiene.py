"""
Il Fantasma v0.02 — hygiene.py
Igiene di processo L2 puntuale (punto 1 della revisione).

- NIENTE mlockall: blocca tutto il processo (client HTTP incluso), consuma
  RLIMIT_MEMLOCK e con MCL_FUTURE ogni allocazione futura diventa lockabile.
  Fallimento = OOM killer o silenzio, non un errore pulito.
- SOLO mlock puntuale sulla regione del secret, dimensione esplicita, risposta
  pagina per pagina: il report dice QUALE pagina e' protetta, ed e' il report
  che sostiene il claim L2 (punto 2).
- RLIMIT_CORE = 0 resta (niente core dump su disco).
- Mai alzare: tutto best-effort con report. Ma il report CONDIZIONA il claim
  (vedi forensics.evaluate_claim): L2 vale solo se hygiene tutto verde.
"""

from __future__ import annotations

import ctypes
import os
import platform
import sys


def _page_size() -> int:
    try:
        if hasattr(os, "sysconf"):
            return int(os.sysconf("SC_PAGE_SIZE"))
    except Exception:
        pass
    return 4096


def apply_process_hygiene() -> dict:
    report: dict = {
        "platform": platform.system(),
        "python": sys.version.split()[0],
        "page_size": _page_size(),
        "policy": "puntuale: solo regione secret via lock_secret_region(), mai mlockall",
    }
    try:
        import resource  # type: ignore

        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        report["rlimit_core"] = "0 (core dump disabilitati)"
        report["rlimit_core_ok"] = True
    except Exception as exc:
        report["rlimit_core"] = f"non applicato ({type(exc).__name__}: {exc})"
        report["rlimit_core_ok"] = False
    # mlockall VOLUTAMENTE assente (vedi docstring). Il lock si fa per-buffer
    # e si riporta per-pagina in lock_secret_region().
    report["mlockall"] = "non usato di proposito (troppo, espone a OOM)"
    report["dontdump"] = "best-effort per-buffer dove supportato"
    return report


def lock_secret_region(buf: bytearray) -> dict:
    """
    mlock puntuale sulla sola regione del secret.
    Ritorna report per-pagina: {locked, bytes, page_size, detail}.
    E' questo report che condiziona L2 (punto 2).
    """
    n = len(buf)
    try:
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        addr = ctypes.addressof(ctypes.c_char.from_buffer(buf))
        rc = libc.mlock(ctypes.c_void_p(addr), ctypes.c_size_t(n))
        if rc == 0:
            return {
                "locked": True,
                "bytes": n,
                "page_size": _page_size(),
                "detail": f"mlock ok su {n} byte",
            }
        err = ctypes.get_errno()
        return {
            "locked": False,
            "bytes": n,
            "page_size": _page_size(),
            "detail": f"mlock errno={err} (servono privilegi/limiti memlock?)",
        }
    except Exception as exc:
        return {
            "locked": False,
            "bytes": n,
            "page_size": _page_size(),
            "detail": f"non applicato ({type(exc).__name__}: {exc})",
        }


def unlock_secret_region(buf: bytearray) -> bool:
    try:
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        addr = ctypes.addressof(ctypes.c_char.from_buffer(buf))
        return libc.munlock(ctypes.c_void_p(addr), ctypes.c_size_t(len(buf))) == 0
    except Exception:
        return False


# alias storici (stessa semantica puntuale)
def lock_buffer(buf: bytearray) -> bool:
    return bool(lock_secret_region(buf).get("locked", False))


def unlock_buffer(buf: bytearray) -> bool:
    return unlock_secret_region(buf)
