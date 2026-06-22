from __future__ import annotations

from app.cache.keys import make_params_hash, normalized_prompt_text
from app.cache.semantic import passes_threshold


def test_threshold_decision():
    assert passes_threshold(0.95, 0.92) is True
    assert passes_threshold(0.92, 0.92) is True   # boundary is a hit
    assert passes_threshold(0.90, 0.92) is False
    assert passes_threshold(None, 0.92) is False


def test_params_hash_is_deterministic_and_param_sensitive():
    base = {"model": "m", "temperature": 0.0, "max_tokens": 100}
    same = {"model": "m", "temperature": 0.0, "max_tokens": 100}
    hot = {"model": "m", "temperature": 0.9, "max_tokens": 100}
    assert make_params_hash(base) == make_params_hash(same)
    assert make_params_hash(base) != make_params_hash(hot)


def test_normalized_prompt_text_flattens_and_normalizes():
    payload = {
        "messages": [
            {"role": "system", "content": "Be Brief"},
            {"role": "user", "content": "  Hello   World "},
        ]
    }
    assert normalized_prompt_text(payload) == "system: be brief user: hello world"
