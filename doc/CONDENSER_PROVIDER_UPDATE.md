# Condenser Provider Update (Historical)

This document is kept for historical reference. The current state is reflected in ARCHITECTURE.md.

## Current State

The condensation module (`src/modules/condenser.py`) supports two providers:

- **OpenAI** (default): model `gpt-5.2`, uses OpenAI Responses API
- **Claude** (optional): model `claude-sonnet-4-20250514`

Configured via `CONDENSER_SERVICE=openai|claude` in `.env`.

OpenAI is the default because it supports the Responses API chain pre-initialization feature
(`init_chains()` in condenser.py, cached in `condenser_chains.json`), which reduces latency
for repeated condensation requests by reusing the system prompt conversation history.

## Original Change (for reference)

OpenAI was added as an alternative to Claude after Claude experienced reliability issues.
OpenAI was made the default at that time. The current default model is `gpt-5.2`.
