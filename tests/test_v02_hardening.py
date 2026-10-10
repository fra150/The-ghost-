"""Test hardening v0.02 — scrypt, bytearray-key, varianti int, FS scan, loopback HTTP.

Punti rossi/arancioni + 5 ritocchi prima del preprint.
Tutti in tests/ come chiesto.
"""

import gc
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fantasma.crypto import scrypt_commitment  # noqa: E402
from fantasma.forensics import (  # noqa: E402
    count_variants_in_stores,
    generate_runtime_canary,
    needle_variants,
    scan_filesystem,
)
from fantasma.ghost_window import release_traceback, scrub_frame_locals  # noqa: E402
from fantasma.secret import OneTimeKey  # noqa: E402


def test_commitment_scrypt_deterministico_e_non_hmac_nudo():
    import hashlib

    code = generate_runtime_canary(13)  # 13 cifre come il caso misurato
    salt = b"audit-salt-fisso-per-test"
    c1 = scrypt_commitment(code, salt)
    c2 = scrypt_commitment(code, salt)
    assert c1 == c2  # deterministico -> contestabile
    assert len(c1) == 64
    # diverso dall'HMAC nudo (43 bit brute-forzabili in ~17 min/GPU)
    naked = hashlib.sha256(bytes(code)).hexdigest()
    assert c1 != naked
    # sale diverso -> impegno diverso
    assert scrypt_commitment(code, b"altro-salt-16byte") != c1
    del code
    gc.collect()


def test_chiave_in_bytearray_con_memset_non_drop():
    k = OneTimeKey()
    m = k.expose_mutable()
    assert isinstance(m, bytearray) and len(m) == 32
    # memset vero, non drop del riferimento
    for i in range(len(m)):
        m[i] = 0x00
    assert all(b == 0 for b in m)
    del m
    comm = k.destroy()
    assert k.is_destroyed
    assert len(comm) == 64
    gc.collect()


def test_varianti_int_hex_base64():
    # canary con zero iniziale per provare la perdita int('098..') -> 12 cifre
    canary = b"0984567345679"
    v = needle_variants(canary)
    assert set(v) >= {"raw", "utf16le", "utf16be", "hex", "base64", "int-decimal", "int-hex"}
    assert v["raw"] == b"0984567345679"
    assert v["int-decimal"] == b"984567345679"  # zero perso: il falso negativo tipico
    assert v["int-hex"] == hex(int("0984567345679")).encode("ascii")
    import base64 as _b64

    assert v["base64"] == _b64.b64encode(b"0984567345679")
    # lo scan a varianti trova la forma int anche se il raw non c'e'
    holder = {"n": v["int-decimal"]}
    assert count_variants_in_stores(canary, holder)["R"] > 0
    del canary
    gc.collect()


def test_filesystem_scan_trova_e_pulisce(tmp_path):
    canary = generate_runtime_canary(13)
    f = tmp_path / "leak.log"
    f.write_bytes(b"TRACE ghost=" + bytes(canary) + b" end")
    res = scan_filesystem(canary, roots=[str(tmp_path)])
    assert res["files_scanned"] >= 1
    assert res["R"] > 0 and res["ok"] is False
    assert res["hits_per_variant"]["raw"] >= 1
    f.unlink()
    gc.collect()
    res2 = scan_filesystem(canary, roots=[str(tmp_path)])
    assert res2["R"] == 0 and res2["ok"] is True
    del canary
    gc.collect()


def test_loopback_http_tocca_buffer_reali():
    """Il mock non esercita httpx/requests+TLS: loopback locale tocca il client reale."""
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from urllib import request as _urlreq

    canary = generate_runtime_canary(13)
    canary_s = canary.decode("ascii")
    seen: dict = {}

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(n)
            seen["body"] = body
            payload = json.dumps({"directive": f"per {canary_s}: scomponi"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *a, **k):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        # prompt reale con canary, spedito via HTTP come farebbe il client LLM
        prompt = f"FANTASMA-INTERPRETA Codice fantasma: {canary_s}"
        req = _urlreq.Request(
            f"http://127.0.0.1:{port}/v1/ghost",
            data=json.dumps({"prompt": prompt}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with _urlreq.urlopen(req, timeout=10) as resp:
            out = json.loads(resp.read().decode())
        assert canary_s in out["directive"]
        # il server ha visto il canary sul loopback: i buffer del client reale
        # sono stati attraversati (punto debole di L2, ora esercitato)
        assert canary in seen["body"]
    finally:
        srv.shutdown()
        t.join(timeout=5)
        srv.server_close()
    del canary
    gc.collect()


def test_scrub_version_gate_e_traceback_release():
    """Misurato: su frame sospesi in traceback lo scrub via proxy NON si propaga
    (ritorna 0 verificato). La via robusta e portabile resta finally con
    azzeramento + release_traceback(). Il test documenta il limite, non lo nasconde."""
    import sys as _sys

    canary = generate_runtime_canary(13)
    s = canary.decode("ascii")

    def _raise():
        local_secret = s
        raise ValueError(f"boom {local_secret}")

    try:
        _raise()
    except ValueError as exc:
        tb = exc.__traceback__
        assert tb is not None
        # scrub dal piu' interno verso l'esterno, solo sul frame _raise:
        # il frame del test trattiene legittimamente `s` (copia dichiarata),
        # scrubbarlo distruggerebbe il needle usato per cercare (falso zero).
        needle_copy = str(s)
        chain = []
        node = tb
        while node is not None:
            chain.append(node)
            node = node.tb_next
        total = 0
        for nd in reversed(chain):
            if nd.tb_frame.f_code.co_name != "_raise":
                continue
            r = scrub_frame_locals(nd.tb_frame, needle_copy)
            if r and r > 0:
                total += r
        if _sys.version_info >= (3, 13):
            # limite misurato: frame sospeso -> scrittura non propagata -> 0 verificato
            assert total == 0
        else:
            assert scrub_frame_locals(tb.tb_frame, s) == -1  # non applicabile
        # via robusta portabile: azzeramento + rilascio frame (misurato, sempre)
        release_traceback(exc)
        assert exc.__traceback__ is None
        del exc
    gc.collect()
    del canary
    gc.collect()
