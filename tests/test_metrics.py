from __future__ import annotations

from app.metering.usage import _percentile


def test_percentile_interpolates():
    vals = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    assert _percentile(vals, 50) == 55.0
    assert _percentile(vals, 0) == 10.0
    assert _percentile(vals, 100) == 100.0


def test_percentile_edge_cases():
    assert _percentile([], 95) == 0.0
    assert _percentile([7], 99) == 7.0


def test_prometheus_render():
    from app import metrics as M

    M.record_hit("exact", 0.01)
    M.observe_request(0.006, "hit")
    M.record_miss(0.002)
    data, content_type = M.render()
    assert b"gateway_requests_total" in data
    assert b"gateway_cache_hits_total" in data
    assert "text/plain" in content_type
