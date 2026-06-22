-- Token-bucket rate limiter, evaluated atomically inside Redis.
-- Running the whole read-modify-write as one script means concurrent requests
-- can't race between checking and decrementing the bucket (no TOCTOU bug).
--
-- KEYS[1] = bucket key (e.g. rl:<api_key>)
-- ARGV    = capacity, refill_per_sec, now_ms, requested
-- Returns = { allowed(1/0), retry_after_ms, tokens_remaining_floor }

local cap    = tonumber(ARGV[1])
local refill = tonumber(ARGV[2])
local now    = tonumber(ARGV[3])
local need   = tonumber(ARGV[4])

local b = redis.call('HMGET', KEYS[1], 'tokens', 'ts')
local tokens = tonumber(b[1])
local ts = tonumber(b[2])

-- First time we've seen this key: start with a full bucket.
if tokens == nil then
    tokens = cap
    ts = now
end

-- Refill based on elapsed time since the last update.
tokens = math.min(cap, tokens + math.max(0, now - ts) / 1000.0 * refill)

local allowed = 0
local retry_ms = 0
if tokens >= need then
    allowed = 1
    tokens = tokens - need
else
    retry_ms = math.ceil((need - tokens) / refill * 1000.0)
end

redis.call('HMSET', KEYS[1], 'tokens', tokens, 'ts', now)
-- Expire idle buckets so we don't leak keys for one-off callers.
redis.call('PEXPIRE', KEYS[1], math.ceil(cap / refill * 1000))

return { allowed, retry_ms, math.floor(tokens) }
