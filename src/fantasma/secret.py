"""
Il Fantasma v0.02 — secret.py
Il codice non deve mai esistere come `str` immutabile.

Decisione v0.02 (da recensioni 1+2):
- il raw numerico vive solo in `bytearray` mutabile, wipabile con memset;
- `str` Python e' immutabile: non esiste memset per una stringa, ogni
  f-string / json.dumps / log / traceback ne crea copie non cancellabili;
- quindi: niente f-string col codice, niente log col codice, __repr__
  mascherato, pickle/serializzazione bloccati, wipe in __del__.

Questo modulo e' la base di L1 (applicativo) + L2 (processo).
L3 (provider/terze parti) resta dichiarato non-garantito con modello remoto.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets


class SecretBytes:
    """
    Contenitore wipabile per il pensiero grezzo (bytes ASCII di cifre).

    - backing: bytearray mutabile (azzerabile);
    - mai esposto come attributo pubblico;
    - __repr__/__str__ non rivelano nulla;
    - pickle/copy bloccati per evitare copie inconsapevoli.
    """

    __slots__ = ("_buf", "_destroyed")

    def __init__(self, buf: bytearray) -> None:
        # prende OWNERSHIP del buffer (non lo copia)
        self._buf = buf
        self._destroyed = False

    @classmethod
    def from_bytes(cls, data: bytes | bytearray) -> "SecretBytes":
        if isinstance(data, bytearray):
            # copia difensiva: il chiamante tiene il suo, noi il nostro
            return cls(bytearray(data))
        return cls(bytearray(data))

    @classmethod
    def from_ascii_digits(cls, digits: bytes) -> "SecretBytes":
        # digits: es. b"0984567345679..." — MAI str
        return cls.from_bytes(digits)

    def __len__(self) -> int:
        return len(self._buf) if not self._destroyed else 0

    def __repr__(self) -> str:
        return f"<SecretBytes len={len(self)} destroyed={self._destroyed}>"

    def __str__(self) -> str:  # mai usare per estrarre il segreto
        raise TypeError("SecretBytes non si converte in str: usare decode_at_boundary().")

    def __bytes__(self) -> bytes:
        raise TypeError("SecretBytes non si converte in bytes implicito: usare expose_copy().")

    def __getstate__(self):
        raise TypeError("SecretBytes non e' serializzabile (no pickle/copy).")

    def __setstate__(self, *_a, **_k):
        raise TypeError("SecretBytes non e' deserializzabile.")

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SecretBytes):
            return NotImplemented
        if self._destroyed or other._destroyed:
            return False
        return hmac.compare_digest(bytes(self._buf), bytes(other._buf))

    # -- uso disciplinato -------------------------------------------------
    def expose_copy(self) -> bytes:
        """Copia bytes esplicita. Usare solo al boundary (es. chiamata LLM) e cancellare subito."""
        if self._destroyed:
            raise ValueError("Secret distrutto.")
        return bytes(self._buf)

    def decode_at_boundary(self) -> str:
        """
        UNICA conversione a str consentita: al boundary verso il modello (5.1).

        AVVISO L2 — leggere prima di dichiarare il claim:
        da qui in poi nascono copie IMMUTABILI non wipabili: la str stessa,
        il payload JSON, i buffer del client HTTP e di TLS, il contesto del
        modello. Il wipe del Secret azzera il bytearray ma NON queste copie.
        Quindi L2 non sara' R=0 appena colleghi il flusso reale: va MISURATO
        con scan_process_mem(), non affermato. Se compare, il claim L2 va
        formulato come "ridotto e misurato", non "garantito".
        Il chiamante DEVE fare `del s` subito dopo l'uso, una sola chiamata.
        """
        if self._destroyed:
            raise ValueError("Secret distrutto.")
        return bytes(self._buf).decode("ascii")

    def commitment(self) -> str:
        """sha256 del contenuto, per audit senza rivelare nulla."""
        if self._destroyed:
            raise ValueError("Secret distrutto: commitment non ricalcolabile (tenere quello in audit).")
        return hashlib.sha256(bytes(self._buf)).hexdigest()

    def is_zeroed(self) -> bool:
        return all(b == 0 for b in self._buf)

    def wipe(self) -> None:
        """Azzeramento a singola passata 0x00 + flag.

        Una passata basta su memoria moderna; le 3 passate non aggiungono
        sicurezza su RAM/swap attuali. In Python l'assegnamento su bytearray
        non viene ottimizzato via (niente elisione come in C), ma resta il
        vincolo vero: il wipe cancella QUESTO buffer, non le copie str/bytes
        create altrove (vedi decode_at_boundary)."""
        if self._destroyed:
            return
        try:
            for i in range(len(self._buf)):
                self._buf[i] = 0x00
        finally:
            self._destroyed = True

    def __del__(self):  # best-effort, mai alzare
        try:
            self.wipe()
        except Exception:
            pass


class OneTimeKey:
    """
    Chiave monouso in RAM per crypto-shredding.

    - nasce con secrets.token_bytes(32), vive in bytearray wipabile;
    - commitment = sha256(chiave) per audit ("e' esistita al tempo T");
    - destroy() la sovrascrive: dopo, il ciphertext e' rumore dimostrabile.
    """

    __slots__ = ("_buf", "_destroyed", "_commitment")

    def __init__(self, nbytes: int = 32) -> None:
        raw = secrets.token_bytes(nbytes)
        self._buf = bytearray(raw)
        self._destroyed = False
        self._commitment = hashlib.sha256(raw).hexdigest()
        # cancella subito l'immutabile d'appoggio
        del raw

    @property
    def commitment(self) -> str:
        return self._commitment

    @property
    def is_destroyed(self) -> bool:
        return self._destroyed

    def expose(self) -> bytes:
        """Copia bytes esplicita (immutabile, NON wipabile). Preferire expose_mutable()."""
        if self._destroyed:
            raise ValueError("Chiave distrutta.")
        return bytes(self._buf)

    def expose_mutable(self) -> bytearray:
        """
        API di basso livello: copia MUTABILE, il chiamante DEVE fare memset.
        E' un contratto (documentato, non imposto): per la garanzia strutturale
        usare SecretRegion (context manager) — wipe sempre, anche su eccezione
        o return anticipata. Vedi punto rosso 3 della revisione."""
        if self._destroyed:
            raise ValueError("Chiave distrutta.")
        return bytearray(self._buf)

    def region(self) -> "SecretRegion":
        """
        Context manager su COPIA di lavoro: il wipe all'uscita azzera la copia,
        la chiave interna resta viva fino a destroy(). Senza copia, il memset
        distruggerebbe la chiave al primo seal (bug)."""
        if self._destroyed:
            raise ValueError("Chiave distrutta.")
        return SecretRegion(bytearray(self._buf))

    def destroy(self) -> str:
        """Azzera la chiave (singola passata, vedi SecretBytes.wipe). Ritorna commitment."""
        if not self._destroyed:
            try:
                for i in range(len(self._buf)):
                    self._buf[i] = 0x00
            finally:
                self._destroyed = True
        return self._commitment

    def __repr__(self) -> str:
        return f"<OneTimeKey destroyed={self._destroyed} commitment={self._commitment[:12]}…>"

    def __getstate__(self):
        raise TypeError("OneTimeKey non serializzabile.")

    def __del__(self):
        try:
            self.destroy()
        except Exception:
            pass


class SecretRegion:
    """
    Punto rosso 3. Il wipe per costruzione, non per contratto.
    expose_mutable() + 'il chiamante DEVE fare memset' e' una convenzione:
    un del distratto o un'eccezione lasciano il buffer leggibile.
    Qui __exit__ fa memset via ctypes SEMPRE (anche su return/eccezione),
    senza sopprimere l'eccezione. Gemello del finally sui frame.

    Uso nella pipeline (obbligatorio):
        with key.region() as buf:  # copia di lavoro, wipata all'uscita
            seal_with_key(buf, pt)  # la chiave interna resta viva fino a destroy()
    """

    __slots__ = ("_b",)

    def __init__(self, buf: bytearray) -> None:
        self._b = buf

    def __enter__(self) -> bytearray:
        return self._b

    def __exit__(self, *exc) -> bool:
        try:
            import ctypes as _ct

            n = len(self._b)
            if n:
                _ct.memset((_ct.c_char * n).from_buffer(self._b), 0, n)
        except Exception:
            try:
                for i in range(len(self._b)):
                    self._b[i] = 0x00
            except Exception:
                pass
        return False
