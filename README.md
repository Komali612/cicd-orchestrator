# my-agent

Starter repo for a new agent. **Clone it, then change a few details** — that's
the whole workflow. No special tooling required.

An agent is: a **prompt** (its role), **skills** (markdown capabilities the LLM
follows), and **tools** (code the LLM can call). The framework (`agent-core`)
runs an LLM tool-use loop over them.

## Create a new agent

1. Clone/copy this repo under your agent's name; set the name in `pyproject.toml`,
   `Makefile`, and `deploy/helm/values.yaml` (and `AGENT_NAME`).
2. Give it a brain: set `AGENT_MODEL` (e.g. `claude-opus-5`) and provide
   `ANTHROPIC_API_KEY`.
3. Edit the three things that define what it does:
   - `src/agent/prompts/system.md` — its role
   - `src/agent/skills/*.md` — its capabilities (plain language)
   - `src/agent/tools/tools.py` — the code it can call

Everything else (wiring, server, Dockerfile, Helm, CI) is inherited from
`agent-core` and rarely touched.

## Run locally

```bash
uv sync
cp .env.example .env          # set AGENT_MODEL + ANTHROPIC_API_KEY for a real brain
uv run agent                  # serves on http://localhost:8080

curl -sX POST localhost:8080/run -H 'content-type: application/json' \
  -d '{"input":"echo hello"}'
```

## Ship (Kubernetes)

```bash
make image
make deploy
```
