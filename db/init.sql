-- Phase 3 schema: semantic cache + usage log.
-- Mounted into the postgres container's init dir AND run at app startup
-- (idempotent), so a fresh DB and an existing one both end up correct.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS prompt_cache (
    id          BIGSERIAL PRIMARY KEY,
    model       TEXT NOT NULL,
    prompt      TEXT NOT NULL,
    params_hash TEXT NOT NULL,              -- temperature/max_tokens/top_p fingerprint
    response    JSONB NOT NULL,
    embedding   VECTOR(384) NOT NULL,       -- all-MiniLM-L6-v2 dim (change if model changes)
    hits        INT DEFAULT 0,
    created_at  TIMESTAMPTZ DEFAULT now(),
    last_hit    TIMESTAMPTZ DEFAULT now()
);

-- Approximate nearest-neighbor index for cosine distance.
CREATE INDEX IF NOT EXISTS prompt_cache_embedding_idx
    ON prompt_cache USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX IF NOT EXISTS prompt_cache_model_idx ON prompt_cache (model);

CREATE TABLE IF NOT EXISTS usage_log (
    id          BIGSERIAL PRIMARY KEY,
    api_key     TEXT,
    model       TEXT,
    cached      BOOLEAN,
    cache_type  TEXT,                       -- exact | semantic | null
    in_tokens   INT,
    out_tokens  INT,
    cost_usd    NUMERIC(10,6),
    saved_usd   NUMERIC(10,6),
    latency_ms  INT,
    created_at  TIMESTAMPTZ DEFAULT now()
);
