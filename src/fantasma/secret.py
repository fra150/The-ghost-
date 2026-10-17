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
    - v0.04: cast numerici bloccati (int/index/float): il codice non e'
      mai un intero (zero iniziale significativo, 63,1 bit).
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

    @classmethod
    def from_canonical_19(cls, buf: bytearray) -> "SecretBytes":
        """Prende OWNERSHIP di un bytearray gia' validato a 19 cifre ASCII.

        Nessuna copia, nessuna conversione intermedia: il chiamante non deve
        piu' toccare `buf` dopo questa chiamata.
        """
        validate_canonical_19(buf)
        obj = cls.__new__(cls)
        obj._buf = buf
        obj._destroyed = False
        return obj

    def __int__(self) -> int:
        raise TypeError("Vietato convertire SecretBytes in intero (perde lo zero iniziale).")

    def __index__(self) -> int:
        raise TypeError("SecretBytes non e' indicizzabile come intero.")

    def __float__(self) -> float:
        raise TypeError("Vietato convertire SecretBytes in float.")

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
            from .bolt import UseAfterDestroyError as _BoltErr

            raise _BoltErr("Secret distrutto: il catenaccio e' chiuso (riuso rilevato).")
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
            from .bolt import UseAfterDestroyError as _BoltErr

            raise _BoltErr("Secret distrutto: il catenaccio e' chiuso (riuso rilevato).")
        return bytes(self._buf).decode("ascii")

    def commitment(self) -> str:
        """sha256 del contenuto, per audit senza rivelare nulla."""
        if self._destroyed:
            from .bolt import UseAfterDestroyError as _BoltErr

            raise _BoltErr("Secret distrutto: commitment non ricalcolabile (tenere quello in audit).")
        return hashlib.sha256(bytes(self._buf)).hexdigest()

    def is_zeroed(self) -> bool:
        return all(b == 0 for b in self._buf)

    def wipe(self) -> bool:
        """Azzeramento a singola passata 0x00 + flag. Ritorna True se ha
        wipato ora, False se era gia' distrutto (idempotente ma rilevabile).

        Una passata basta su memoria moderna; le 3 passate non aggiungono
        sicurezza su RAM/swap attuali. In Python l'assegnamento su bytearray
        non viene ottimizzato via (niente elisione come in C), ma resta il
        vincolo vero: il wipe cancella QUESTO buffer, non le copie str/bytes
        create altrove (vedi decode_at_boundary).
        v0.04: usa secure_wipe_buffer centralizzato (stessa semantica)."""
        if self._destroyed:
            return False
        try:
            try:
                from .hygiene import secure_wipe_buffer as _wipe

                _wipe(self._buf)
            except Exception:
                for i in range(len(self._buf)):
                    self._buf[i] = 0x00
        finally:
            self._destroyed = True
        return True

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
            from .bolt import UseAfterDestroyError as _BoltErr

            raise _BoltErr("Chiave distrutta: il catenaccio e' chiuso (riuso rilevato).")
        return bytes(self._buf)

    def expose_mutable(self) -> bytearray:
        """
        API di basso livello: copia MUTABILE, il chiamante DEVE fare memset.
        E' un contratto (documentato, non imposto): per la garanzia strutturale
        usare SecretRegion (context manager) — wipe sempre, anche su eccezione
        o return anticipata. Vedi punto rosso 3 della revisione."""
        if self._destroyed:
            from .bolt import UseAfterDestroyError as _BoltErr

            raise _BoltErr("Chiave distrutta: il catenaccio e' chiuso (riuso rilevato).")
        return bytearray(self._buf)

    def region(self) -> "SecretRegion":
        """
        Context manager su COPIA di lavoro: il wipe all'uscita azzera la copia,
        la chiave interna resta viva fino a destroy(). Senza copia, il memset
        distruggerebbe la chiave al primo seal (bug)."""
        if self._destroyed:
            from .bolt import UseAfterDestroyError as _BoltErr

            raise _BoltErr("Chiave distrutta: il catenaccio e' chiuso (riuso rilevato).")
        return SecretRegion(bytearray(self._buf))

    def destroy(self) -> str:
        """Azzera la chiave (singola passata, vedi SecretBytes.wipe). Ritorna commitment."""
        if not self._destroyed:
            try:
                try:
                    from .hygiene import secure_wipe_buffer as _wipe

                    _wipe(self._buf)
                except Exception:
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
            from .hygiene import secure_wipe_buffer as _wipe

            _wipe(self._b)
        except Exception:
            try:
                for i in range(len(self._b)):
                    self._b[i] = 0x00
            except Exception:
                pass
        return False


CODE_DIGITS = 19  # canonico v0.04: 63,1 bit nominali se uniforme


def validate_canonical_19(buf: bytes | bytearray) -> None:
    """Valida 19 cifre ASCII direttamente sul buffer, senza copie str/int.

    Controlla byte a byte (0x30-0x39). Non crea mai str/int dell'intero
    codice: `bytes(buf)` qui sotto e' solo vista per il confronto, mai
    convertita in numero.
    """
    if len(buf) != CODE_DIGITS:
        raise ValueError(f"Il codice deve avere esattamente {CODE_DIGITS} cifre, non {len(buf)}.")
    for b in buf:
        if b < 0x30 or b > 0x39:
            raise ValueError("Il codice deve contenere solo cifre ASCII 0-9.")


def digest_to_canonical_19(digest: bytes) -> bytearray:
    """Deriva 19 cifre uniformi da un digest, con rejection sampling.

    v0.04: sostituisce il vecchio `f"{b:03d}"` troncato (biasato).
    Ogni byte del digest (o dei blocchi SHA256 a catena se servono piu'
    byte) con valore >= 250 viene scartato, gli altri danno % 10.
    Scrive le cifre ASCII direttamente nel bytearray, senza mai formare
    int o str dell'intero codice.
    Deterministico a parita' di digest (il fantasma resta legato all'input).
    """
    out = bytearray(CODE_DIGITS)
    pos = 0
    ctr = 0
    seed = bytes(digest)
    while pos < CODE_DIGITS:
        block = hashlib.sha256(seed + ctr.to_bytes(4, "big")).digest()
        ctr += 1
        for b in block:
            if b >= 250:
                continue
            out[pos] = 0x30 + (b % 10)
            pos += 1
            if pos >= CODE_DIGITS:
                break
    del seed
    return out


def random_canonical_19() -> bytearray:
    """Genera 19 cifre uniformi da CSPRNG, senza int/str dell'intero codice.

    Usa secrets.token_bytes a blocchi + rejection sampling (>= 250 scartato),
    scrive le cifre ASCII direttamente nel bytearray. MAI secrets.randbelow
    sull'intero 10**19 (creerebbe un int non azzerabile con l'intero codice).
    Il chiamante deve trasferire subito l'ownership a SecretBytes.
    """
    out = bytearray(CODE_DIGITS)
    pos = 0
    while pos < CODE_DIGITS:
        for b in secrets.token_bytes(32):
            if b >= 250:
                continue
            out[pos] = 0x30 + (b % 10)
            pos += 1
            if pos >= CODE_DIGITS:
                break
    return out
