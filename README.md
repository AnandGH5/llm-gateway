# LLM Gateway

A proxy that sits between your app and an LLM provider like OpenAI. You point your
client at this instead of the provider and it forwards the request. On top of that it
caches responses (both identical and *similar* prompts) so repeated calls are served
instantly and for free, and it tracks cost so you can see what the cache saves.

Phases 1–3 are done. What's left is rate limiting, provider failover, and a dashboard.

## What's here so far

- `POST /v1/chat/completions` in the normal OpenAI format
- a mock provider so you can run it with no API key, plus a real openai provider
- streaming works (`"stream": true`)
- **exact cache** (Redis) — identical prompts served in single-digit ms
- **semantic cache** (pgvector) — paraphrases hit too, e.g. "Tell me France's capital"
  matches "What's the capital of France?"
- cost metering + `/stats` (hit rate, cost saved vs spent, tokens)
- `X-Cache` (`HIT-EXACT` / `HIT-SEMANTIC` / `MISS`), `X-Cache-Similarity`, `X-Cost-Saved-USD`
- bearer key auth
- Docker + compose (gateway + redis + postgres/pgvector)

## Running it

Needs Docker. Copy the env file and bring it all up:

```bash
cp .env.example .env
docker compose up --build
```

Gateway is on http://localhost:8000; Redis and Postgres come up alongside it. The
default provider is the mock one, so no API key is needed. (The first request that uses
the semantic cache loads the embedding model, which can take a few seconds the first time.)

Exact cache — send the same message twice:

```bash
curl -i http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer gw_sk_demo123" -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"What is the capital of France?"}]}'
# repeat -> X-Cache: HIT-EXACT
```

Semantic cache — now ask the same thing a different way:

```bash
curl -i http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer gw_sk_demo123" -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"Tell me France'\''s capital"}]}'
# -> X-Cache: HIT-SEMANTIC, plus X-Cache-Similarity
```

Check the running totals:

```bash
curl http://localhost:8000/stats
```

## Using it from the OpenAI SDK

You only change the base url:

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8000/v1", api_key="gw_sk_demo123")
r = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "hello"}],
)
print(r.choices[0].message.content)
```

To hit the real OpenAI instead of the mock, set in `.env`:

```bash
PRIMARY_PROVIDER=openai
OPENAI_API_KEY=sk-...
```

## Tuning the semantic cache

`SIMILARITY_THRESHOLD` (default 0.92) controls how close a paraphrase must be to count as a
hit. Lower = more hits but more risk of a wrong answer; higher = safer but fewer hits. Every
lookup logs its best similarity so you can pick a value from real traffic.

## Running without Docker

You'll want Redis and Postgres (with pgvector) available, but the gateway degrades
gracefully if they're not — caches just turn into misses and it still proxies.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt    # note: pulls torch for local embeddings (heavy)
cp .env.example .env
uvicorn app.main:app --reload
```

## Tests

```bash
pytest -q
```

Tests use an in-memory fake Redis and skip the database tier, so no servers (and no model
download) are needed to run them.

## Layout

```
app/
  main.py            app + health/root, mounts routes, runs the schema migration
  config.py          settings from env
  models.py          request schema
  deps.py            shared redis client
  db.py              postgres/pgvector pool + migration
  api/chat.py        /v1/chat/completions (exact -> semantic -> provider, write-through)
  api/stats.py       /stats
  auth/              bearer key check
  cache/             keys.py, exact.py (Redis), embeddings.py, semantic.py (pgvector)
  metering/          pricing.py, cost.py, usage.py (redis counters)
  providers/         mock, openai, and the router that picks one
db/init.sql          pgvector extension + tables
tests/
docs/                phase write-ups
```

## TODO

- rate limiting (token bucket) and provider failover
- a small stats dashboard
