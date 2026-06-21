# LLM Gateway

A proxy that sits between your app and an LLM provider like OpenAI. You point your
client at this instead of the provider and it forwards the request. On top of that it
caches responses so repeated calls are served instantly and for free, and it tracks
cost so you can see what the cache saves.

Right now phases 1 and 2 are done. Caching is exact-match for now; semantic caching,
rate limiting and failover come next.

## What's here so far

- `POST /v1/chat/completions` in the normal OpenAI format
- a mock provider so you can run it with no API key, plus a real openai provider
- streaming works (`"stream": true`)
- exact-match response cache in Redis with a TTL
- cost metering, and a `/stats` endpoint (hit rate, cost saved vs spent, tokens)
- `X-Cache` / `X-Cost-Saved-USD` response headers
- bearer key auth
- Docker + compose (gateway + redis)

## Running it

Needs Docker. Copy the env file and bring it up:

```bash
cp .env.example .env
docker compose up --build
```

Gateway is on http://localhost:8000, Redis comes up alongside it. Default provider is
the mock one so no key is needed.

Send the same message twice and watch the second one hit the cache:

```bash
# first call -> X-Cache: MISS
curl -i http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer gw_sk_demo123" -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"hello"}]}'

# same call again -> X-Cache: HIT-EXACT, plus X-Cost-Saved-USD
curl -i http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer gw_sk_demo123" -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"hello"}]}'
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

## Running without Docker

You'll need a Redis running somewhere (or just point `REDIS_URL` at one). The cache
degrades to "always miss" if Redis isn't reachable, so the gateway still works without it.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

## Tests

```bash
pytest -q
```

The tests use an in-memory fake Redis, so no server is needed to run them.

## Layout

```
app/
  main.py            app + health/root, mounts the routes
  config.py          settings from env
  models.py          request schema
  deps.py            shared redis client
  api/chat.py        /v1/chat/completions (cache lookup + write-through + metering)
  api/stats.py       /stats
  auth/              bearer key check
  cache/             exact-match cache: keys.py, exact.py
  metering/          pricing.py, cost.py, usage.py (redis counters)
  providers/         mock, openai, and the router that picks one
tests/
docs/                phase write-ups
```

## TODO

- semantic cache with pgvector (catch paraphrases, not just identical prompts)
- rate limiting and provider failover
- a small stats dashboard
