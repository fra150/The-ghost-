"""Passo 2: implementa la specifica prodotta dal Fantasma. Chiamata diretta (esecutore)."""
import re
import sys
from pathlib import Path

sys.path.insert(0, "src")

from fantasma import make_deepseek_llm

spec = Path("outputs/live_code_output.md").read_text(encoding="utf-8")
llm = make_deepseek_llm()

prompt = (
    "Implementa COMPLETAMENTE la specifica qui sotto in un unico file Python "
    "eseguibile, solo libreria standard. Restituisci UN solo blocco ```python "
    "completo e funzionante (funzioni + test con assert in if __name__ == '__main__'). "
    "Niente stub con '...', niente puntini, tutto il codice reale.\n\n"
    "SPEC:\n" + spec
)
out = llm(prompt)
Path("outputs/live_code_impl.md").write_text(out, encoding="utf-8")

blocchi = [b.strip() for b in re.compile(r"```python(.*?)```", re.S).findall(out)]
print("blocchi=", len(blocchi), "len_output=", len(out), flush=True)
code_parts = [b for b in blocchi if "def " in b and "..." not in b or "assert" in b]
codice = "\n\n".join(code_parts if code_parts else blocchi).strip() + "\n"
Path("outputs/prezzi_fix.py").write_text(codice, encoding="utf-8")
print("salvato righe=", len(codice.splitlines()), flush=True)
print("--- ANTEPRIMA ---")
print(codice[:1200])
