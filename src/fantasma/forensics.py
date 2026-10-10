"""
Il Fantasma v0.02 — forensics.py
La scomparsa diventa un test verde, non una convinzione.

Metrica v0.02: residuo R = copie in (store applicativi + file + mem processo).
Obiettivo: R = 0 entro il perimetro del processo (L1+L2).
L3 (provider/terze parti) dichiarato non-garantito con modello remoto.

NOTA TECNICA ONESTA (scoperta in test su Windows):
bytes/str/bytearray NON sono tracciati dal gc Python, quindi
`gc.get_objects()` non li contiene mai. La scansione heap via gc
sottostima sempre (trova 0 anche quando il segreto esiste).
Il metodo corretto e' la lettura di /proc/self/mem su Linux
(come nel tuo esperimento: baseline 3, prompt 10, dopo wipe 8,
31 con letterali). Qui forniamo entrambe:
- conta in store noti (portabile, L1) — sempre valido;
- scansione /proc/self/mem (Linux, L2) — il numero vero.
Su Windows la seconda ritorna None (non disponibile) e il test
verifica L1 + zeroing del Secret, dichiarandolo.

REGOLA: canary SEMPRE generati a runtime con secrets, MAI letterali
nel sorgente — altrimenti misuri il sorgente (effetto "31 copie").
"""

from __future__ import annotations

import gc
import os
import secrets


def generate_runtime_canary(n_digits: int = 19) -> bytes:
    """Canary numerico ASCII generato a runtime. MAI scriverlo come letterale."""
    return "".join(str(secrets.randbelow(10)) for _ in range(n_digits)).encode("ascii")


def count_needle_in_heap_via_gc(needle: bytes) -> int:
    """
    DEPRECATO come misura: bytes/str non sono gc-tracked, ritorna quasi
    sempre 0. Tenuto per documentare il limite. Usare scan_process_mem()
    su Linux o count_needle_in_stores() ovunque.
    """
    gc.collect()
    count = 0
    try:
        needle_str: str | None = needle.decode("ascii")
    except Exception:
        needle_str = None
    for obj in gc.get_objects():
        try:
            if isinstance(obj, (bytes, bytearray)):
                if obj is not needle and bytes(obj).find(needle) != -1:
                    count += 1
            elif isinstance(obj, str) and needle_str is not None:
                if needle_str in obj and obj is not needle_str:
                    count += 1
        except Exception:
            continue
    return count


# alias storico
count_needle_in_heap = count_needle_in_heap_via_gc


def count_needle_in_text(needle: bytes, text: str | bytes) -> int:
    if isinstance(text, str):
        try:
            return 1 if needle.decode("ascii") in text else 0
        except Exception:
            return 0
    return 1 if bytes(text).find(bytes(needle)) != -1 else 0


def needle_variants(needle: bytes) -> dict[str, bytes]:
    """
    Tutte le codifiche in cui il canary puo' sopravvivere (punto 6):
    raw ASCII, UTF-16LE/BE, hex, base64, int-decimal (zero iniziale perso),
    int-hex. 'Non trovato' vale solo per cio' che cerchi.
    REGOLA: il codice del Fantasma non e' mai un intero — resta stringa di
    cifre a lunghezza fissa, zeri iniziali significativi. Le varianti int
    servono a intercettare serializzazioni scorrette (JSON numero, %d)."""
    out: dict[str, bytes] = {"raw": bytes(needle)}
    try:
        s = bytes(needle).decode("ascii")
        out["utf16le"] = s.encode("utf-16-le")
        out["utf16be"] = s.encode("utf-16-be")
        out["hex"] = s.encode("ascii").hex().encode("ascii")
        import base64 as _b64

        out["base64"] = _b64.b64encode(s.encode("ascii"))
        # int-decimal: int(s) perde lo zero iniziale; int-hex la forma 0x...
        try:
            out["int-decimal"] = str(int(s)).encode("ascii")
            out["int-hex"] = hex(int(s)).encode("ascii")
        except ValueError:
            pass
    except Exception:
        pass
    return out


def count_variants_in_stores(needle: bytes, *stores) -> dict:
    """Cerca raw+utf16+hex+base64+int negli store. Ritorna {variante: hits, R, ok}."""
    per: dict[str, int] = {}
    for name, var in needle_variants(needle).items():
        per[name] = count_needle_in_stores(var, *stores)
    r = sum(per.values())
    return {"per_variant": per, "R": r, "ok": r == 0}


def count_needle_in_stores(needle: bytes, *stores) -> int:
    """
    Conta le occorrenze del canary negli store applicativi noti:
    dict/list/tuple/str/bytes e oggetti con __dict__/__slots__.
    E' la misura L1 portabile: dopo amnesia deve essere 0.
    L'oggetto `needle` stesso passato come store viene escluso.
    """
    try:
        needle_str = needle.decode("ascii")
    except Exception:
        needle_str = None
    found = 0
    seen: set[int] = set()

    def visit(o) -> None:
        nonlocal found
        if o is needle or id(o) in seen:
            return
        seen.add(id(o))
        try:
            if isinstance(o, bytes | bytearray):
                if bytes(o).find(needle) != -1:
                    found += 1
            elif isinstance(o, str):
                if needle_str is not None and needle_str in o:
                    found += 1
            elif isinstance(o, dict):
                for k, v in list(o.items()):
                    visit(k)
                    visit(v)
            elif isinstance(o, (list, tuple, set, frozenset)):
                for v in list(o):
                    visit(v)
            elif hasattr(o, "__dict__"):
                try:
                    visit(vars(o))
                except Exception:
                    pass
            if hasattr(o, "__slots__"):
                try:
                    slots = o.__slots__  # type: ignore
                    if isinstance(slots, str):
                        slots = (slots,)
                    for s in slots:
                        try:
                            visit(object.__getattribute__(o, s))
                        except Exception:
                            pass
                except Exception:
                    pass
        except Exception:
            pass

    for s in stores:
        visit(s)
    return found


def scan_process_mem(needle: bytes, variants: bool = True) -> dict | None:
    """
    Scansione vera della memoria via /proc/self/mem (Linux).
    Con variants=True cerca raw + utf16le/be: ritorna dict {variante: hits}.
    Ritorna None se non disponibile (Windows/macOS senza /proc).
    Metodo del tuo esperimento (baseline 3, prompt 10, wipe 8)."""
    if not os.path.exists("/proc/self/mem") or not os.path.exists("/proc/self/maps"):
        return None
    targets = needle_variants(needle) if variants else {"raw": bytes(needle)}
    try:
        # leggi tutte le regioni leggibili una volta sola, poi cerca le varianti
        blobs: list[bytes] = []
        with open("/proc/self/maps", "r") as maps, open("/proc/self/mem", "rb", buffering=0) as mem:
            for line in maps:
                parts = line.split()
                if len(parts) < 1:
                    continue
                rng, *perms = parts
                if not perms or "r" not in perms[0]:
                    continue
                try:
                    start_s, end_s = rng.split("-")
                    start, end = int(start_s, 16), int(end_s, 16)
                except ValueError:
                    continue
                size = end - start
                if size <= 0 or size > 256 * 1024 * 1024:
                    continue
                try:
                    mem.seek(start)
                    chunk = mem.read(size)
                    if chunk:
                        blobs.append(chunk)
                except Exception:
                    continue
        per: dict[str, int] = {}
        for name, var in targets.items():
            per[name] = sum(1 for c in blobs if c.find(var) != -1)
        per["_regions_scanned"] = len(blobs)
        return per
    except Exception:
        return None


def scan_filesystem(needle: bytes, roots: list[str] | None = None, max_bytes_per_file: int = 2_000_000) -> dict:
    """
    Punto 1 (L1). R=0 solo sugli store dichiarati e' circolare: restano fuori
    logging, __pycache__, output pytest, tmp, log, eccezioni su file.
    Scansione portabile (anche Windows) di cwd+temp+log nelle 7 codifiche.
    L1 = store dichiarati + file system scansionato.
    Ritorna {files_scanned, hits_per_variant, R, ok, roots}.
    """
    import pathlib
    import tempfile

    if roots is None:
        roots = [str(pathlib.Path.cwd()), tempfile.gettempdir()]
    variants = needle_variants(needle)
    hits: dict[str, int] = {k: 0 for k in variants}
    files_scanned = 0
    skip_dirs = {"__pycache__", ".git", ".pytest_cache", "node_modules", ".venv"}
    for root in roots:
        try:
            base = pathlib.Path(root)
            if not base.exists():
                continue
            # se root e' un file, scansiona solo lui
            candidates = [base] if base.is_file() else list(base.rglob("*"))
        except Exception:
            continue
        for p in candidates:
            try:
                if not p.is_file():
                    continue
                if any(d in p.parts for d in skip_dirs) and p.suffix in (".pyc", ".pyo"):
                    continue
                if p.stat().st_size > 20_000_000:
                    continue
                data = p.read_bytes()[:max_bytes_per_file]
                files_scanned += 1
                for name, var in variants.items():
                    if var and data.find(var) != -1:
                        hits[name] += 1
            except Exception:
                continue
    r = sum(hits.values())
    return {"files_scanned": files_scanned, "hits_per_variant": hits, "R": r, "ok": r == 0, "roots": roots}


def compute_R(heap_copies: int, cache_copies: int = 0, file_copies: int = 0) -> dict:
    """Storico: R grezzo. Per il claim usare evaluate_claim() con guardia hygiene."""
    r = int(heap_copies) + int(cache_copies) + int(file_copies)
    return {"R": r, "heap": heap_copies, "cache": cache_copies, "files": file_copies, "ok": r == 0}


def count_unexpected(needle: bytes, stores: tuple | list, n_legitimate: int) -> dict:
    """
    Punto 3. R = copie_trovate - copie_legittime_dichiarate.
    Lo scanner possiede il canary per cercarlo: quella copia e' legittima
    e va sottratta, altrimenti R misura se stesso.
    assert R == 0 significa 'nessuna copia oltre quelle che so di avere'.
    """
    found = count_needle_in_stores(needle, *stores) if stores else 0
    unexpected = max(0, found - int(n_legitimate))
    return {
        "found": found,
        "legitimate": int(n_legitimate),
        "R": unexpected,
        "ok": unexpected == 0,
    }


def count_variants_unexpected(needle: bytes, stores: tuple | list, n_legitimate_per_variant: dict | None = None) -> dict:
    """Come count_unexpected ma per raw+utf16le/be."""
    n_legitimate_per_variant = n_legitimate_per_variant or {}
    per: dict[str, dict] = {}
    for name, var in needle_variants(needle).items():
        found = count_needle_in_stores(var, *stores) if stores else 0
        legit = int(n_legitimate_per_variant.get(name, 0))
        per[name] = {"found": found, "legitimate": legit, "R": max(0, found - legit)}
    r = sum(v["R"] for v in per.values())
    return {"per_variant": per, "R": r, "ok": r == 0}


def _hygiene_all_green(report: dict) -> bool:
    """
    Punto 2+4. L2 vale solo se hygiene tutto verde:
    rlimit ok AND lock puntuale riuscito. Il lock dice 'regione designata
    protetta', NON 'nessuna copia in swap' (punto 4): le copie fuori regione
    (str/JSON/HTTP) non sono lockate."""
    try:
        if report.get("rlimit_core_ok") is not True:
            return False
        lock = report.get("last_lock") or {}
        # su Linux serve lock riuscito; su Windows (no libc) L2 resta non-misurabile
        # e la guardia resta rossa di proposito (vedi evaluate_claim).
        return bool(lock.get("locked", False))
    except Exception:
        return False


def evaluate_claim(store_R: int, hygiene_report: dict, mem_scan: dict | None) -> dict:
    """
    Punto 2+7. Il claim e' condizionale, non una frase sola:
    - L1 sempre affermabile (dipende solo dai tuoi store);
    - L2 affermabile SOLO se hygiene verde E mem_scan disponibile e pulito;
    - L3 mai affermato.
    R=0 significa 'zero copie inattese entro i confini misurabili'.
    """
    l1_ok = int(store_R) == 0
    hyg_ok = _hygiene_all_green(hygiene_report or {})
    if mem_scan is None:
        l2_status = "non-misurabile (no /proc: Windows/macOS)"
        l2_ok = False
    else:
        hits = sum(v for k, v in mem_scan.items() if not k.startswith("_"))
        l2_status = f"misurato: {hits} regioni con copie inattese" if hits else "misurato: 0 copie inattese"
        l2_ok = hyg_ok and hits == 0
    return {
        "L1_store_R0": bool(l1_ok),
        "L1_claim": "affermabile" if l1_ok else "NON affermato (residuo negli store)",
        "hygiene_green": bool(hyg_ok),
        "L2_mem": mem_scan,
        "L2_status": l2_status,
        "L2_claim": "affermabile entro confini misurabili" if l2_ok else "NON affermato",
        "L3_claim": "mai affermato: provider/rete/kernel fuori controllo",
        "overall": bool(l1_ok and l2_ok),
        "boundary": "R=0 entro i confini misurabili del processo",
    }


def assert_scanner_sane(needle: bytes) -> None:
    """
    Punto 4. Controlli obbligatori anti-falso-zero (lo scan su gc mente a favore):
    - positivo: copia nota iniettata DEVE essere trovata;
    - negativo: store vuoto DEVE dare zero.
    Senza positivo, R=0 non significa niente. Il nostro L1 non usa gc
    (attraversa gli store dichiarati) proprio per evitare il punto cieco.
    """
    probe = {"p": bytes(needle).decode("ascii")}
    assert count_needle_in_stores(needle, probe) >= 1, "controllo positivo fallito: scanner cieco"
    assert count_needle_in_stores(needle, {}) == 0, "controllo negativo fallito"
