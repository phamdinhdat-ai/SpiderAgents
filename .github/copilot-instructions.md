# SpiderAgents / OpenSpider — Copilot Instructions

> **Primary instructions file:** [`AGENTS.md`](../AGENTS.md) — read that first.

## Quick Reference

- **Active target:** `src/openspider/` (never modify `src/qwenpaw/` unless explicitly asked)
- **Build:** `pip install -e ".[dev]"` then `make test-unit` / `make quick` / `make test`
- **Env vars:** `OPENSPIDER_*` canonical, `QWENPAW_*`/`COPAW_*` legacy fallback via `_get_env()` in `constant.py`
- **Full docs:** [`README_openspider.md`](../README_openspider.md)
