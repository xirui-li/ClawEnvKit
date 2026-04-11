# Roadmap

This file tracks concrete follow-up work that affects benchmark quality,
runtime reliability, or repository ergonomics.

## Runtime Reliability

- [ ] Fix `web_real` and `web_real_injection` search imports in multi-service mode.
  Impact: cross-service tasks that load `web_real` through `multi_server.py`
  can silently lose real search capability and return empty `/web/search`
  results, which biases evaluation scores downward.
  Scope: replace fragile `from search_serp import search_serp` imports with
  package-safe imports that work under dynamic module loading in
  `agent_loop_eval.py`, Docker multi-service entrypoints, and any other
  `mock_services.<svc>.server` import path.
