# llm-gateway
A proxy that sits between your app and an LLM provider like OpenAI. You point your client at this instead of the provider and it forwards the request. The idea is to build caching, rate limiting, cost tracking and failover on top, so repeated or similar prompts get served from a cache instead of hitting the provider every time.
