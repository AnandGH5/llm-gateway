#!/usr/bin/env python3
"""Benchmark the LLM Gateway with a realistic mixed workload.

Builds a prompt stream with a controlled repeat/paraphrase/unique ratio (the
shape of real FAQ/support traffic), fires it at the gateway, and reports cache
hit rate, cost reduction, and the cached-vs-uncached latency contrast. Then a
short burst phase shows the rate limiter returning 429s.

Run the gateway first (ideally with MOCK_LATENCY_MS set so misses are slow and
the contrast is visible), e.g.:

    MOCK_LATENCY_MS=600 docker compose up --build
    python benchmark/run.py --n 300 --concurrency 10

Talks only to the mock provider by default, so it costs nothing.
"""
from __future__ import annotations

import argparse
import asyncio
import random
import time

import httpx

# A small bank of base questions, each with a few paraphrases.
BANK: dict[str, list[str]] = {
    "What is the capital of France?": [
        "Tell me France's capital",
        "Which city is the capital of France?",
        "France's capital city is what?",
    ],
    "How do I reverse a string in Python?": [
        "What's the way to reverse a string in Python?",
        "Reverse a string using Python — how?",
        "In Python, how can I flip a string backwards?",
    ],
    "What is the boiling point of water?": [
        "At what temperature does water boil?",
        "Tell me water's boiling point",
        "Water boils at what temperature?",
    ],
    "Who wrote Romeo and Juliet?": [
        "Romeo and Juliet was written by whom?",
        "Which author wrote Romeo and Juliet?",
        "Name the writer of Romeo and Juliet",
    ],
    "What is the speed of light?": [
        "How fast does light travel?",
        "Tell me the speed of light",
        "Light travels at what speed?",
    ],
}
SEEDS = list(BANK.keys())


def build_workload(n: int, repeat: float = 0.4, paraphrase: float = 0.2) -> list[str]:
    """repeat% exact repeats of seeds, paraphrase% paraphrases, rest unique."""
    out: list[str] = []
    for i in range(n):
        r = random.random()
        if r < repeat:
            out.append(random.choice(SEEDS))                      # exact repeat
        elif r < repeat + paraphrase:
            q = random.choice(SEEDS)
            out.append(random.choice(BANK[q]))                    # paraphrase
        else:
            out.append(f"Unique question #{i}: {random.choice(SEEDS)} (variant {random.random():.6f})")
    random.shuffle(out)
    return out


def _pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * (p / 100.0)
    import math
    lo, hi = math.floor(k), math.ceil(k)
    if lo == hi:
        return s[int(k)]
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


async def _send(client: httpx.AsyncClient, url: str, key: str, prompt: str):
    t0 = time.perf_counter()
    try:
        resp = await client.post(
            url,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": "gemini-3.1-flash-lite", "messages": [{"role": "user", "content": prompt}]},
        )
        ms = (time.perf_counter() - t0) * 1000.0
        return resp.status_code, resp.headers.get("x-cache", "MISS"), ms
    except Exception:
        return 0, "ERROR", (time.perf_counter() - t0) * 1000.0


async def run_phase(url: str, key: str, prompts: list[str], concurrency: int):
    sem = asyncio.Semaphore(concurrency)
    results = []

    async def worker(p):
        async with sem:
            results.append(await _send(client, url, key, p))

    async with httpx.AsyncClient(timeout=30.0) as client:
        await asyncio.gather(*(worker(p) for p in prompts))
    return results


def report(results: list[tuple[int, str, float]]):
    exact = [ms for code, xc, ms in results if xc == "HIT-EXACT"]
    semantic = [ms for code, xc, ms in results if xc == "HIT-SEMANTIC"]
    miss = [ms for code, xc, ms in results if xc == "MISS"]
    hits = len(exact) + len(semantic)
    total = len(results)

    def line(name, lats):
        if not lats:
            print(f"  {name:<16} {0:>6}   {'—':>8} {'—':>8} {'—':>8}")
            return
        print(f"  {name:<16} {len(lats):>6}   {_pct(lats,50):>7.1f}ms {_pct(lats,95):>7.1f}ms {_pct(lats,99):>7.1f}ms")

    print("\n=== Results ===")
    print(f"  total requests : {total}")
    print(f"  hit rate       : {hits/total*100:.1f}%  (exact {len(exact)}, semantic {len(semantic)})")
    print(f"  misses         : {len(miss)}")
    print(f"\n  {'bucket':<16} {'count':>6}   {'p50':>8} {'p95':>8} {'p99':>8}")
    print("  " + "-" * 52)
    line("cache HIT", exact + semantic)
    line("  exact", exact)
    line("  semantic", semantic)
    line("cache MISS", miss)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000/v1/chat/completions")
    ap.add_argument("--stats-url", default="http://localhost:8000/stats")
    ap.add_argument("--key", default="gw_sk_demo123")
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--concurrency", type=int, default=10)
    ap.add_argument("--burst", type=int, default=120, help="rapid requests to trigger 429s (0 to skip)")
    args = ap.parse_args()

    print(f"Sending {args.n} requests at concurrency {args.concurrency} …")
    prompts = build_workload(args.n)
    results = await run_phase(args.url, args.key, prompts, args.concurrency)
    report(results)

    # Pull server-side cost numbers.
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            s = (await client.get(args.stats_url)).json()
        print(f"\n  cost saved     : ${s['cost_saved_usd']:.4f}")
        print(f"  cost spent     : ${s['cost_spent_usd']:.4f}")
        print(f"  cost reduction : {s['cost_reduction_pct']:.1f}%")
    except Exception as e:
        print(f"\n  (couldn't read /stats: {e})")

    # Burst phase: hammer one prompt to trip the limiter.
    if args.burst:
        print(f"\n=== Burst phase ({args.burst} rapid requests) ===")
        burst_prompts = ["ping"] * args.burst
        burst = await run_phase(args.url, args.key, burst_prompts, concurrency=args.burst)
        codes = [c for c, _, _ in burst]
        print(f"  200 OK         : {codes.count(200)}")
        print(f"  429 limited    : {codes.count(429)}")


if __name__ == "__main__":
    asyncio.run(main())
