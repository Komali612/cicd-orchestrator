"""Orchestrator direct service — submit a repo URL, get back a real PR.

This is the demo path and it deliberately **bypasses the LLM brain**: the console
POSTs the real repo URL + GitHub token to ``POST /ci``, and the orchestrator
forwards that straight to the running NetcoreCIAgent's ``/ci`` endpoint (at
``CI_AGENT_URL``). The CI agent discovers -> generates -> validates -> opens a
real pull request, and its result (including the PR URL) is returned here.

    orchestrator UI  ──POST /ci──▶  orchestrator  ──HTTP──▶  NetcoreCIAgent /ci  ──▶  PR

    GET  /         the orchestrator console
    GET  /healthz  liveness (also echoes the CI agent target)
    POST /ci       {repo_url, github_token, options, selected_tools} -> CI agent
    POST /cd       (not wired in this demo unless CD_AGENT_URL is set)

Run it (two processes, distinct ports):

    # 1) the CI agent, in agent-ci-workers/netcore-ci-agent
    AGENT_PORT=8001 uv run ci-serve

    # 2) this orchestrator, in agent-orchestrators/netcore-orchestrator
    AGENT_PORT=8000 CI_AGENT_URL=http://127.0.0.1:8001 uv run orch-serve

Then open http://127.0.0.1:8000, paste a GitHub URL + token, click Run CI.
"""
from __future__ import annotations

import os
from typing import Any

import requests
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .console import CONSOLE_HTML

app = FastAPI(title="netcore-orchestrator", version="0.1.0")

DEFAULT_CI_AGENT_URL = "http://127.0.0.1:8001"


def _ci_agent_url() -> str:
    return os.getenv("CI_AGENT_URL", DEFAULT_CI_AGENT_URL).rstrip("/")


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
    return {"status": "ok", "agent": "netcore-orchestrator", "ci_agent_url": _ci_agent_url()}


@app.post("/ci", tags=["ci"])
def ci(req: CIRequest) -> dict:
    """Forward the request to the CI agent's /ci and return its result verbatim.

    We pass the values straight through (this is the direct, non-LLM channel), so
    the real GitHub token reaches the CI agent that actually opens the PR. On a
    transport failure we return a clear, actionable error instead of a stack
    trace — and never echo the token.
    """
    target = _ci_agent_url() + "/ci"
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
            "error": (
                f"Could not reach the CI agent at {target} "
                f"({type(exc).__name__}). Is `ci-serve` running and is "
                f"CI_AGENT_URL correct?"
            ),
        }
    try:
        data = resp.json()
    except ValueError:
        return {
            "status": "error",
            "stage": "ci_agent",
            "http_status": resp.status_code,
            "error": resp.text[:500],
        }
    if isinstance(data, dict):
        data.setdefault("via", "netcore-orchestrator")
        return data
    return {"status": "ok", "via": "netcore-orchestrator", "result": data}


@app.post("/cd", tags=["cd"])
def cd(req: CIRequest) -> dict:
    """CD is not part of this demo wiring. If a CD agent is available, set
    CD_AGENT_URL and we forward to it; otherwise return a clear notice."""
    cd_url = os.getenv("CD_AGENT_URL")
    if not cd_url:
        return {
            "status": "not_wired",
            "agent": "NetcoreCDAgent",
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
