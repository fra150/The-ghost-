"""Test adapter DeepSeek — tutto mockato, nessuna chiamata reale, nessuna chiave vera."""

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import fantasma.llm_deepseek as ld  # noqa: E402


class _FakeCompletions:
    def __init__(self, outer):
        self.outer = outer

    def create(self, **kwargs):
        self.outer.captured = kwargs
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Hello dal Fantasma-Flash"))]
        )


class _FakeChat:
    def __init__(self, outer):
        self.completions = _FakeCompletions(outer)


class _FakeOpenAI:
    last: " _FakeOpenAI | None" = None

    def __init__(self, api_key="", base_url=""):
        self.api_key = api_key
        self.base_url = base_url
        self.chat = _FakeChat(self)
        self.captured: dict = {}
        _FakeOpenAI.last = self


def _patch(monkeypatch, env: dict):
    for k in ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL",
              "DEEPSEEK_REASONING_EFFORT", "DEEPSEEK_THINKING", "DEEPSEEK_SYSTEM"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import openai as _openai_mod

    monkeypatch.setattr(_openai_mod, "OpenAI", _FakeOpenAI, raising=False)
    # evita che load_env rilegga un .env vero durante i test
    monkeypatch.setattr(ld, "load_env", lambda *a, **k: None)


def test_make_deepseek_llm_chiama_deepseek_flash_con_thinking(monkeypatch):
    _patch(monkeypatch, {"DEEPSEEK_API_KEY": "sk-test-finto"})
    llm = ld.make_deepseek_llm()
    out = llm("Hello")

    assert out == "Hello dal Fantasma-Flash"
    fake = _FakeOpenAI.last
    assert fake is not None
    assert fake.api_key == "sk-test-finto"
    assert fake.base_url == "https://api.deepseek.com"
    cap = fake.captured
    # modello canonico DeepSeek-V4.1-Flash
    assert cap["model"] == "deepseek-flash"
    assert cap["stream"] is False
    assert cap["reasoning_effort"] == "high"
    assert cap["extra_body"] == {"thinking": {"type": "enabled"}}
    ruoli = [m["role"] for m in cap["messages"]]
    assert ruoli == ["system", "user"]
    assert cap["messages"][1]["content"] == "Hello"


def test_manca_chiave_errore_chiaro(monkeypatch):
    _patch(monkeypatch, {})
    try:
        ld.make_deepseek_llm()
    except RuntimeError as exc:
        assert "DEEPSEEK_API_KEY" in str(exc)
    else:
        raise AssertionError("doveva alzare RuntimeError senza chiave")


def test_fantasma_pipeline_accetta_llm_deepseek_mockato(monkeypatch):
    _patch(monkeypatch, {"DEEPSEEK_API_KEY": "sk-test-finto"})
    from fantasma import FantasmaPipeline

    pipe = FantasmaPipeline(llm_fn=ld.make_deepseek_llm())
    res = pipe.process(
        "Spiega perché questa decisione strategica è complessa, confronta alternative e valuta rischi?"
    )
    assert res.ghost_activated is True
    assert res.used_same_ai is True
    assert "Hello dal Fantasma-Flash" in res.output
    assert res.memory_empty_after and res.cache_empty_after
