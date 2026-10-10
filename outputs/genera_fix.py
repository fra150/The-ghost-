"""Genera fix live via Fantasma + DeepSeek, estrae i blocchi python, li salva."""
import re
import sys
from pathlib import Path

sys.path.insert(0, "src")

from fantasma import FantasmaPipeline, make_deepseek_llm

TESTO = (
    "Dammi la versione COMPLETA e finale, pronta da eseguire, della funzione "
    "prezzi carrello corretta. Requisiti: niente default mutabili, niente IndexError, "
    "niente divisione per zero (carrello vuoto = ValueError chiaro), valida sconto 0-100, "
    "usa Decimal per il denaro, separa validazione e calcolo, includi test essenziali "
    "con assert eseguibili. Restituisci tutto in uno o piu blocchi python pronti da "
    "salvare in file. Spiega prima in 3 righe le scelte, poi il codice."
)

pipe = FantasmaPipeline(llm_fn=make_deepseek_llm())
r = pipe.process(TESTO)
print("ghost=", r.ghost_activated, "audit=", r.audit_ok,
      "mem=", r.memory_empty_after, "cache=", r.cache_empty_after, flush=True)

out_dir = Path("outputs")
out_dir.mkdir(exist_ok=True)
(out_dir / "live_code_output.md").write_text(
    "# OUTPUT LIVE FANTASMA\n\n" + r.output, encoding="utf-8"
)

pattern = re.compile(r"```python(.*?)```", re.S)
blocchi = [b.strip() for b in pattern.findall(r.output)]
print("blocchi_python_trovati=", len(blocchi), flush=True)
if not blocchi:
    print("NESSUN BLOCCO PYTHON ESTRAIBILE", flush=True)
    raise SystemExit(1)

codice = "\n\n".join(blocchi).strip() + "\n"
target = out_dir / "prezzi_fix.py"
target.write_text(codice, encoding="utf-8")
print("salvato", target, "righe=", len(codice.splitlines()), flush=True)
