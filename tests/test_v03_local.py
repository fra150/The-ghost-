"""Test offline per adapter Ollama e statistica v0.03 (nessuna rete)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fantasma.bench_gsm8k_v03 import bootstrap_diff, mcnemar, wrap_metered
from fantasma.llm_ollama import make_ollama_llm


class _FakeClient:
    def __init__(self, fail_once=False):
        self.calls = 0
        self.fail_once = fail_once
        self.last_kw = None

    def generate(self, *a, **kw):
        self.calls += 1
        self.last_kw = kw
        model = kw.get("model", (a[0] if a else None))
        assert model == "gemma4"
        if self.fail_once and self.calls == 1:
            raise ConnectionError("boom")
        return {"response": "#### 8", "eval_count": 5, "prompt_eval_count": 12,
                "total_duration": 2_000_000_000}


def test_adapter_ok_e_stats():
    llm = make_ollama_llm(client=_FakeClient())
    assert llm("domanda") == "#### 8"
    assert llm.stats == {"eval": 5, "prompt_eval": 12, "ms": 2000}


def test_adapter_retry_una_volta():
    llm = make_ollama_llm(client=_FakeClient(fail_once=True))
    assert llm("domanda") == "#### 8"  # secondo tentativo


def test_adapter_propaga_dopo_due_fallimenti():
    class _SempreRotto:
        def generate(self, *a, **kw):
            raise TimeoutError("giù")

    llm = make_ollama_llm(client=_SempreRotto())
    try:
        llm("x")
        raise AssertionError("doveva alzare")
    except TimeoutError:
        pass


def test_adapter_think_usa_raw_http(monkeypatch):
    import fantasma.llm_ollama as m

    seen: dict = {}

    def fake_raw(host, model, prompt, options, think, timeout):
        seen.update(host=host, model=model, think=think, options=options)
        return "#### 8", {"eval": 3, "prompt_eval": 9, "ms": 100}

    monkeypatch.setattr(m, "_raw_generate", fake_raw)
    llm = make_ollama_llm(think=False, num_predict=64)
    assert llm("domanda") == "#### 8"
    assert seen["think"] is False and seen["options"]["num_predict"] == 64
    assert llm.stats == {"eval": 3, "prompt_eval": 9, "ms": 100}


def test_wrap_metered_accumula():
    llm = make_ollama_llm(client=_FakeClient())
    fn, log = wrap_metered(llm)
    fn("a")
    fn("b")
    assert len(log) == 2 and all(e["eval"] == 5 for e in log)


def test_mcnemar_nessun_disaccordo():
    r = mcnemar(0, 0)
    assert r["p"] == 1.0 and r["method"] == "no-discordant"


def test_mcnemar_chi2():
    r = mcnemar(20, 8)  # n=28: chi2 = (12-1)^2/28 = 4.3214
    assert r["method"] == "chi2-cc"
    assert abs(r["chi2"] - 4.3214) < 1e-3
    assert 0.03 < r["p"] < 0.05  # significativo ad alfa 0.05


def test_mcnemar_esatto_piccoli():
    r = mcnemar(5, 0)
    assert r["method"] == "exact-binomial"
    assert r["p"] <= 0.0625 + 1e-9


def test_bootstrap_diff_zero():
    a = [True, False] * 10
    d = bootstrap_diff(a, list(a), iters=500, seed=1)
    assert d["diff"] == 0.0 and d["ci95"][0] <= 0.0 <= d["ci95"][1]
