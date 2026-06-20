# LLM Gateway

A proxy that sits between your app and an LLM provider like OpenAI. You point your
client at this instead of the provider and it forwards the request. The idea is to
build caching, rate limiting, cost tracking and failover on top, so repeated or
similar prompts get served from a cache instead of hitting the provider every time.

This is phase 1, which is just the proxy part working end to end. The caching and
the rest come after.

## What's here so far

- `POST /v1/chat/completions` using the normal OpenAI request format
- a mock provider so you can run it with no API key
- an openai provider that forwards to the real API
- streaming works (`"stream": true`)
- bearer key auth
- Dockerfile and compose file

## Running it

You need Docker. Copy the example env file and bring it up:

```bash
cp .env.example .env
docker compose up --build
```

It listens on http://localhost:8000. The default provider is the mock one, so you
don't need any key to try it.

Health check:

```bash
curl http://localhost:8000/health
```

Send a message:

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer gw_sk_demo123" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"hello"}]}'
```

Add `-i` to the curl if you want to see the `X-Cache` and `X-Provider` headers.

Streaming:

```bash
curl -N http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer gw_sk_demo123" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"hi"}],"stream":true}'
```

## Using it from the OpenAI SDK

The whole point is that you only change the base url:

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8000/v1", api_key="gw_sk_demo123")
r = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "hello"}],
)
print(r.choices[0].message.content)
```

To hit the real OpenAI instead of the mock, put these in `.env`:

```bash
PRIMARY_PROVIDER=openai
OPENAI_API_KEY=sk-...
```

## Running without Docker

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

## Layout

```
app/
  main.py          app + health endpoint
  config.py        settings read from env
  models.py        request schema
  api/chat.py      the /v1/chat/completions endpoint
  auth/            bearer key check
  providers/       mock, openai, and the router that picks one
tests/
```

## TODO

- exact-match cache + cost tracking
- semantic cache with pgvector
- rate limiting and provider failover
- a stats endpoint / small dashboard
