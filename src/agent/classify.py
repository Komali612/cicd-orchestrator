"""Classify a repository into a tech stack so the orchestrator can route it.

The orchestrator authors nothing itself (ARCHITECTURE.md §2.1) — it inspects the
repo and forwards to whichever worker agent owns that stack. Classification reads
the ``.csproj`` files, because the stacks are structurally distinct:

  * .NET Framework 4.x  -> ``<TargetFrameworkVersion>v4.x</TargetFrameworkVersion>``
                           (old-style, usually packages.config)  -> ``netfx48``
  * .NET Core / .NET 5+ -> ``<Project Sdk="Microsoft.NET.Sdk">`` and/or
                           ``<TargetFramework>net6.0/net7.0/net8.0…`` -> ``netcore``

Mixed repos (e.g. an FX web app plus an SDK-style installer helper) are decided by
the PRIMARY application project — test/installer helpers are skipped — so a repo
like Fiserve (v4.8 web app + a net10 MsiBuilder) classifies as ``netfx48``.

No agent-core dependency, so this is unit-testable offline.
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
from typing import Optional

_AUX = re.compile(r"(?:^|/)(?:.*\.tests?\.csproj$|.*test.*|installer/|msibuilder)", re.IGNORECASE)

_FX_RE = re.compile(r"<TargetFrameworkVersion>\s*v([0-9.]+)\s*</TargetFrameworkVersion>", re.IGNORECASE)
_SDK_RE = re.compile(r'Sdk\s*=\s*"Microsoft\.NET\.Sdk', re.IGNORECASE)
_TFM_RE = re.compile(r"<TargetFrameworks?>\s*([^<]+)</TargetFrameworks?>", re.IGNORECASE)


def _is_aux(rel_path: str) -> bool:
    """True for test / installer helper projects that must not decide the stack."""
    low = rel_path.lower()
    return ("test" in low) or ("/installer/" in low) or ("msibuilder" in low)


def _classify_csproj(content: str) -> Optional[str]:
    """'netfx48' | 'netcore' | None for a single .csproj's XML."""
    if _FX_RE.search(content):
        return "netfx48"
    if _SDK_RE.search(content):
        return "netcore"
    m = _TFM_RE.search(content)
    if m:
        tfm = m.group(1).lower()
        if "netcoreapp" in tfm or re.search(r"net(\d+)\.", tfm) or re.search(r"net(\d+)-", tfm):
            return "netcore"
        if re.match(r"^\s*v?4\.", tfm):
            return "netfx48"
    return None


def classify_local_tree(root: str) -> dict:
    """Classify an already-checked-out tree. Returns the routing decision."""
    projects: list[dict] = []
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in files:
            if not f.lower().endswith(".csproj"):
                continue
            rel = os.path.relpath(os.path.join(dirpath, f), root).replace(os.sep, "/")
            try:
                content = open(os.path.join(dirpath, f), "r", encoding="utf-8-sig").read()
            except Exception:
                content = ""
            projects.append({"path": rel, "stack": _classify_csproj(content), "aux": _is_aux(rel)})

    classified = [p for p in projects if p["stack"]]
    primary = [p for p in classified if not p["aux"]] or classified

    if not primary:
        return {"stack": "unknown", "reason": "no .NET project (.csproj) with a recognizable target framework found",
                "primary_target": None, "projects": projects}

    # Primary application project decides the stack; report a mix if it exists.
    stacks = {p["stack"] for p in primary}
    chosen = primary[0]
    stack = chosen["stack"]
    reason = f"primary project {chosen['path']} -> {stack}"
    if len(stacks) > 1:
        reason += f" (repo also contains other stacks: {sorted(stacks)}; routing by primary)"
    return {"stack": stack, "reason": reason, "primary_target": chosen["path"], "projects": projects}


def classify_repo(repo_url: str, branch: str = "main") -> dict:
    """Shallow-clone ``repo_url`` and classify it. On a clone failure returns
    ``stack='unknown'`` with the error (the orchestrator then routes nowhere)."""
    try:
        with tempfile.TemporaryDirectory() as tmp:
            dest = os.path.join(tmp, "repo")
            subprocess.run(
                ["git", "clone", "--depth", "1", "--branch", branch, repo_url, dest],
                check=True, capture_output=True, timeout=60,
            )
            result = classify_local_tree(dest)
            result["repo_url"] = repo_url
            result["branch"] = branch
            return result
    except subprocess.CalledProcessError as e:
        return {"stack": "unknown", "reason": f"clone failed: {e.stderr.decode('utf-8', 'ignore')[:200] if e.stderr else e}",
                "primary_target": None, "repo_url": repo_url, "branch": branch}
    except Exception as e:
        return {"stack": "unknown", "reason": f"classification failed: {e}",
                "primary_target": None, "repo_url": repo_url, "branch": branch}
