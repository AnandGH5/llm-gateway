from __future__ import annotations

from app.cache.keys import is_cacheable, make_cache_key
from app.metering.cost import compute_cost
from app.metering.pricing import price_for


def _payload(content, **extra):
    return {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": content}], **extra}


def test_identical_prompts_share_a_key():
    assert make_cache_key(_payload("Hello")) == make_cache_key(_payload("Hello"))


def test_normalization_ignores_case_and_whitespace():
    a = make_cache_key(_payload("What's the capital of France?"))
    b = make_cache_key(_payload("  what's   the CAPITAL of france? "))
    assert a == b


def test_different_model_yields_different_key():
    p1 = _payload("Hello")
    p2 = _payload("Hello")
    p2["model"] = "gpt-4o"
    assert make_cache_key(p1) != make_cache_key(p2)


def test_different_params_yield_different_key():
    base = _payload("Hello")
    hot = _payload("Hello", temperature=0.9)
    assert make_cache_key(base) != make_cache_key(hot)


def test_paraphrase_is_NOT_an_exact_hit():
    # Exact cache must not collapse different wordings — that's Phase 3's job.
    a = make_cache_key(_payload("What's the capital of France?"))
    b = make_cache_key(_payload("Tell me France's capital"))
    assert a != b


def test_cacheability_rules():
    assert is_cacheable(_payload("hi")) is True
    assert is_cacheable(_payload("hi", temperature=1.5), max_temperature=1.0) is False
    assert is_cacheable(_payload("hi", n=2)) is False
    assert is_cacheable(_payload("hi", no_cache=True)) is False


def test_cost_math():
    # gpt-4o-mini = (0.00015 in, 0.0006 out) per 1k tokens
    cost = compute_cost("gpt-4o-mini", 1000, 1000)
    assert abs(cost - (0.00015 + 0.0006)) < 1e-9


def test_unknown_model_uses_default_price():
    assert price_for("some-unknown-model") == (0.0005, 0.0015)


def test_dated_model_id_matches_base():
    assert price_for("gpt-4o-2024-08-06") == price_for("gpt-4o")
