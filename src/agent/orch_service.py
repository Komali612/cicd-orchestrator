"""Orchestrator direct service — submit a repo URL, get back a real PR.

This is the demo path and it deliberately **bypasses the LLM brain**. The console
POSTs the real repo URL + GitHub token to ``POST /ci``; the orchestrator
**classifies** the repo (.NET Core vs .NET FX 4.8) and **routes** it to the
matching CI agent's ``/ci`` endpoint. That agent discovers -> generates ->
validates -> opens a real pull request, and its result (incl. the PR URL) is
returned here. The orchestrator authors nothing itself (ARCHITECTURE.md §2.1).

    orchestrator UI ─POST /ci─▶ orchestrator ─classify─▶ route to matching agent /ci ─▶ PR

    GET  /         the orchestrator console
    GET  /healthz  liveness (also echoes the agent registry)
    POST /ci       {repo_url, github_token, options, selected_tools} -> matching CI agent
    POST /cd       (not wired in this demo unless CD_AGENT_URL is set)

Run it (distinct ports), e.g.:

    # the CI agents
    AGENT_PORT=8001 uv run ci-serve                 # netcore-ci-agent
    AGENT_PORT=8002 uv run ci-serve                 # netfx48-ci-agent

    # this orchestrator, pointed at both
    AGENT_PORT=8000 NETCORE_CI_AGENT_URL=http://127.0.0.1:8001 \
      NETFX48_CI_AGENT_URL=http://127.0.0.1:8002 uv run orch-serve
"""
from __future__ import annotations

import os
from typing import Any

import requests
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .classify import classify_repo
from .console import CONSOLE_HTML

app = FastAPI(title="cicd-orchestrator", version="0.2.0")


def _agent_registry() -> dict[str, str]:
    """stack -> that stack's CI-agent /ci base URL. Per-client/per-deployment via
    env; sensible localhost defaults on distinct ports. CI_AGENT_URL stays as a
    backward-compatible fallback for the netcore agent."""
    netcore = os.getenv("NETCORE_CI_AGENT_URL") or os.getenv("CI_AGENT_URL") or "http://127.0.0.1:8001"
    netfx48 = os.getenv("NETFX48_CI_AGENT_URL") or "http://127.0.0.1:8002"
    return {"netcore": netcore.rstrip("/"), "netfx48": netfx48.rstrip("/")}


class CIRequest(BaseModel):
    repo_url: str
    github_token: str = ""
    options: dict[str, Any] = {}
    selected_tools: dict[str, Any] = {}


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def home() -> str:
    return CONSOLE_HTML


@app.get("/healthz", tags=["ops"])
def healthz() -> dict:
    return {"status": "ok", "agent": "cicd-orchestrator", "agents": _agent_registry()}


@app.post("/ci", tags=["ci"])
def ci(req: CIRequest) -> dict:
    """Classify the repo, then forward to the matching CI agent's /ci.

    Values pass straight through (the direct, non-LLM channel), so the real
    GitHub token reaches the agent that opens the PR. A repo we can't classify is
    NOT forwarded — it comes back as an exception-list entry for a human.
    """
    registry = _agent_registry()
    branch = (req.options or {}).get("branch", "main")

    decision = classify_repo(req.repo_url, branch=branch)
    stack = decision.get("stack")
    if stack not in registry:
        # Unclassifiable / unsupported -> exception list (routes nowhere).
        return {
            "status": "unclassified",
            "stage": "orchestrator-classify",
            "classification": decision,
            "message": (
                f"Could not route {req.repo_url!r}: classified as {stack!r}. "
                "Added to the exception list for human review. "
                f"Supported stacks: {sorted(registry)}."
            ),
        }

    target = registry[stack] + "/ci"
    payload = {
        "repo_url": req.repo_url,
        "github_token": req.github_token,
        "options": req.options or {},
        "selected_tools": req.selected_tools or {},
    }
    try:
        resp = requests.post(target, json=payload, timeout=180)
    except requests.RequestException as exc:
        return {
            "status": "error",
            "stage": "orchestrator->ci_agent",
            "classified_as": stack,
            "routed_to": target,
            "error": (
                f"Classified as {stack} but could not reach its CI agent at {target} "
                f"({type(exc).__name__}). Is that agent's `ci-serve` running and is "
                f"{'NETCORE_CI_AGENT_URL' if stack == 'netcore' else 'NETFX48_CI_AGENT_URL'} correct?"
            ),
        }
    try:
        data = resp.json()
    except ValueError:
        return {"status": "error", "stage": "ci_agent", "classified_as": stack,
                "routed_to": target, "http_status": resp.status_code, "error": resp.text[:500]}
    if isinstance(data, dict):
        data.setdefault("via", "cicd-orchestrator")
        data["classified_as"] = stack
        data["classification_reason"] = decision.get("reason")
        data["routed_to"] = target
        return data
    return {"status": "ok", "via": "cicd-orchestrator", "classified_as": stack,
            "routed_to": target, "result": data}


@app.post("/cd", tags=["cd"])
def cd(req: CIRequest) -> dict:
    """CD is not part of this demo wiring. If a CD agent is available, set
    CD_AGENT_URL and we forward to it; otherwise return a clear notice."""
    cd_url = os.getenv("CD_AGENT_URL")
    if not cd_url:
        return {
            "status": "not_wired",
            "message": "CD wiring is out of scope for this demo. Set CD_AGENT_URL to enable it.",
        }
    try:
        resp = requests.post(cd_url.rstrip("/") + "/cd", json=req.model_dump(), timeout=180)
        return resp.json()
    except Exception as exc:  # noqa: BLE001 - surface a clean message
        return {"status": "error", "error": f"{type(exc).__name__}: {exc}"}


def main() -> None:
    import uvicorn

    from agent_core.config import settings

    uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
