# Hermes-Lite Integration Guide

> Applies to the Hermes-Lite runtime pinned by `../AGENTS.md` and the upstream
> lock manifest `../upstream-hermes.json`. This guide covers Dazah integration,
> not a second version source.

## Architecture

Hermes-Lite provides a compact agent runtime with a conservative default tool
surface:

```text
Application / Web API
        |
        v
Hermes-Lite Agent Core
        |
        +-- conversation loop
        +-- provider resolution
        +-- prompt assembly
        +-- memory/session helpers
        +-- tool registry
        |
        +-- default tools:
            web_search / web_extract / memory / session_search / todo / clarify
```

## Installation

For Dazah development, use the workspace root `.env.local`, `compose.dev.yml`
and `Dockerfile.dev`. Confirm the backend development database is migrated and
`app` is healthy before starting `hermes-lite`. Do not store model-provider
API keys inside Hermes-Lite.

## Configuration

- `config.yaml` contains the default provider and runtime settings.
- The workspace root `.env.local` supplies development configuration; variable
  names and examples are maintained in root `.env.example` and
  `.env.local.example`.
- Runtime state such as sessions, memories, and caches should stay local and is
  ignored by git.

## Dazah Central Agent Adapter

Dazah uses Hermes-Lite as an independent orchestration service behind the Dazah
backend Agent gateway:

```text
Dazah frontend floating assistant
        |
        v
Dazah backend /api/v1/agent/chat
        |
        v
Hermes-Lite services.dazah_agent_service:/v2/agent/runs
        |
        +-- LLM: Dazah /api/v1/agent/llm/chat/completions
        +-- Tool discovery: Dazah /api/v1/agent/tools/search
        +-- Tool describe: Dazah /api/v1/agent/tools/{operation}
        +-- Tool execute: Dazah /api/v1/agent/tools/execute
```

For local Dazah development, run the root development Compose stack from the
workspace root after confirming the backend is healthy:

```bash
docker compose --env-file .env.local -f compose.dev.yml up -d --build hermes-lite
```

The root development Compose file mounts the repository into `/app` and starts
Uvicorn with `--reload`, so Python source edits are picked up automatically
after the first image build. Rebuild only when dependencies, Dockerfile, or
entrypoint files change.

When running inside the Dazah production compose network, use service names
instead of localhost:

```bash
DAZAH_API_BASE_URL=http://app:8000/api/v1
DAZAH_LLM_BASE_URL=http://app:8000/api/v1/agent/llm
```

Security boundaries:

- In Dazah central-agent deployment, Hermes-Lite only receives
  service-to-service tokens, not model-provider keys.
- The active text model is resolved by Dazah backend from the platform LLM
  configuration table on every request.
- The `dazah` toolset only calls the Dazah Agent tool gateway.
- The backend module registry and Tool Registry define available operations.
  Write confirmations, business permissions, audit records, Feishu credentials,
  and transactions stay in the Dazah backend.

## Toolsets

| Toolset | Tools | Notes |
|---------|-------|-------|
| `agent` | `web_search`, `web_extract`, `memory`, `session_search`, `todo`, `clarify` | Default lightweight surface |
| `web` | `web_search`, `web_extract` | Public web research |
| `memory` | `memory` | Durable preferences and facts |
| `session_search` | `session_search` | Past session recall |
| `todo` | `todo` | Task planning |
| `clarify` | `clarify` | Clarifying questions |
| `skills` | `skill_manage` | Administrator/developer opt-in only |
| `dazah` | `dazah_tool` | Dynamic Dazah backend tool catalog, scoped to the trusted subject |

## Removed Business Extensions

Hermes-Lite intentionally does not ship tender/bid-intelligence extensions:

- no tender search or recommendation tools
- no company-to-tender matching tools
- no six-dimension scoring model
- no win-probability prediction
- no OceanBase-backed RAG schema or ingestion CLI
- no business sample datasets

These can be added later as separate plugins or application-layer services if a
deployment needs them.

## Operational Notes

- Keep `.env`, memory files, and local runtime state out of version control.
- Enable administrator-only tools explicitly instead of adding them to the
  default `agent` toolset.
- Treat browser, terminal, file mutation, code execution, process, cron, and
  delegate tools as non-default capabilities.

## Smoke Check

```bash
python -m py_compile run_agent.py model_tools.py toolsets.py
```
