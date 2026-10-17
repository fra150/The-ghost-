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


def secure_wipe_buffer(buf: bytearray | memoryview) -> None:
    """Azzera un buffer mutabile. v0.04 P1: refactor centralizzato.

    NOTA ONESTA (non presentarlo nel paper come miglioramento di L2):
    ctypes.memset e' gia' una chiamata opaca via FFI che nessun compilatore
    puo' elidere. Il valore qui e' centralizzare i 4 loop di wipe copiati
    (SecretBytes/OneTimeKey/SecretRegion/CryptoShredder) in un punto unico.
    Tenta explicit_bzero (Linux) / SecureZeroMemory (Windows) dove esportati,
    altrimenti memset deterministico. `from_buffer` pinna il resize: il
    riferimento C viene rilasciato in finally.
    """
    if not isinstance(buf, (bytearray, memoryview)):
        raise TypeError("Il buffer deve essere mutabile (bytearray o memoryview).")
    n = len(buf)
    if n == 0:
        return
    c_buf = None
    try:
        c_buf = (ctypes.c_char * n).from_buffer(buf)
        wiped = False
        if sys.platform.startswith("linux"):
            try:
                libc = ctypes.CDLL("libc.so.6")
                if hasattr(libc, "explicit_bzero"):
                    libc.explicit_bzero(c_buf, n)
                    wiped = True
            except (AttributeError, OSError):
                pass
        elif sys.platform == "win32":
            try:
                kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
                for name in ("RtlSecureZeroMemory", "SecureZeroMemory"):
                    fn = getattr(kernel32, name, None)
                    if fn is not None:
                        try:
                            fn(c_buf, n)
                            wiped = True
                            break
                        except Exception:
                            continue
            except (AttributeError, OSError):
                pass
        if not wiped:
            ctypes.memset(c_buf, 0, n)
    finally:
        # Rilascia il pin sul buffer (sblocca il resize del bytearray).
        try:
            del c_buf
        except Exception:
            pass


# alias storici (stessa semantica puntuale)
def lock_buffer(buf: bytearray) -> bool:
    return bool(lock_secret_region(buf).get("locked", False))


def unlock_buffer(buf: bytearray) -> bool:
    return unlock_secret_region(buf)
