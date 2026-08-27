# ARCHITECTURE & WORKING CONTEXT — Agentic CI/CD Platform

> **READ THIS FIRST.** This is the single source of truth for any Claude Code session
> or coding agent working on this project. It captures what we're building, the
> authoritative architecture, how the repositories are organized, how the pieces
> interact, and the working methodology to follow. If something here conflicts with
> what you find in code, **this file + the architect's docs win** — the code has
> drifted in places (see "Current state vs. target").

---

## 1. What we're building (the big picture)

An **agentic CI/CD (and Testing) automation platform** for a **service company that
serves many clients**. You point it at a Git repository (or a list, or a whole org)
and specialized agents **generate the CI/CD pipeline, validate it, and open a pull
request for a human to review and merge**. Agents never merge their own PRs.

This is a **marketplace / catalog model**, and it drives every structural decision:

- **Each agent is a self-contained microservice in its own repository**, deployable
  independently.
- **Each agent carries its own "cookbook"** — the library of deterministic pipeline
  recipes **scoped to only that one framework** (the .NET Core CI agent ships .NET
  Core recipes only; the .NET FX 4.8 CI agent ships .NET FX 4.8 recipes only).
- **The orchestrator is separate from the agents and is per-client.** Each client
  deploys the **subset of agents** they need plus **their own orchestrator**, which
  **classifies** each incoming repo and **routes** it to whichever agents that client
  has deployed.
- All agents are stamped from **shared scaffolding** (`agent-core` + `agent-starter`).

**The unit of everything is: one repo per agent + a separate orchestrator repo +
shared scaffolding.** A bundled monorepo is the *wrong* shape for this model (fine
for a demo, wrong for production).

---

## 2. Authoritative architecture

Source of truth = the architect's documents:
`Agent_Acceptance_Criteria_v1.1.docx` and `FIG Agentic Flow (1).pdf` (companion to the
"Requirements Document — Agentic CI/CD Pipeline Automation v2.0" PRD). Deployed on
**GKE**, in two namespaces (CICD, TEST).

### 2.1 Two subsystems

**A. CI/CD subsystem**
```
                 ┌──────────────────────┐
  repo / list /  │   CICD Orchestrator  │  classify → route  (authors NOTHING itself)
  git org  ────▶ │  (per-client, generic)│  unclassifiable → exception list
                 └──────────┬───────────┘
        ┌───────────────────┼─────────────────────┐
        ▼                   ▼                      ▼
   NetCoreCI           NetLegacyCI            Cobol*CI  (pending)   + PlaywrightCI
   NetCoreCD           NetLegacyCD            Cobol*CD  (pending)
   (.NET Core 6/7/8)   (.NET FX 4.8)          (COBOL IBM i / Unisys)
```
- **CD runs only after the matching CI succeeds** for that repo.
- **10 CI/CD agents total** at target: Orchestrator + 4 CI (NetCoreCI, NetLegacyCI,
  CobolIBMCI, CobolUnisysCI) + 1 PlaywrightCI + 4 CD (NetCoreCD, NetLegacyCD,
  CobolIBMCD, CobolUnisysCD). **COBOL agents are pending / not built yet.**

**B. Testing subsystem** (separate Testing Orchestrator, separate namespace)
```
Jira Story Review → BDD Generator → Playwright Generator → Test Validator → Defect Creator
                    (+ Relearn agent, Knowledge-Graph DB, Vector DB)
```
Produces Gherkin + Playwright tests; the Playwright test repos feed the CD agents'
deployment validation. **Not started in code yet.**

### 2.2 The worker-agent lifecycle (every CI and CD agent follows this)

```
1. DISCOVER  — read the repo on GitHub: language, framework, build/deploy needs,
               existing pipeline, required tools.
2. GENERATE  — COOKBOOK-FIRST: find the matching recipe in this agent's own cookbook
               and render deterministically. LLM is used ONLY as a fallback when no
               cookbook matches (and to write the missing cookbook entry).
               Idempotent: if a pipeline already exists, add/modify ONLY the missing
               or deficient steps; keep human edits — never blind-regenerate.
3. VALIDATE  — lint + a real GitHub Actions test run (the PR's own CI run IS the
               check; no separate sandbox). On failure, revise and retry, up to a
               MAX of 3 attempts, then write the repo to the exception list.
4. DELIVER   — commit the pipeline to the repo (standard folder structure) and open a
               PULL REQUEST for human review. THE AGENT NEVER MERGES ITS OWN PR.
```

### 2.3 What "cookbook" means and where it lives

A **cookbook** = the agent's library of **known-good, per-framework pipeline recipes**
(the parts that differ per stack: toolchain setup, build/test commands, scanners,
artifact/dockerfile). The agent uses it to generate deterministically; the LLM only
fills gaps.

**Location rule (authoritative):** the cookbook lives **inside the agent repo that
owns that framework.** NOT in the orchestrator (it authors nothing), NOT in
`agent-core`/`agent-starter` (they're framework-agnostic), NOT in a shared store.
- Example: the architect's **.NET FX 4.8 CI YAML** belongs in the **`netlegacy-ci-agent`
  repo's cookbook.** Until that repo exists, its **interim home is `cicd-bootstrap`**
  (`src/cicd_bootstrap/cookbooks/cookbooks.yaml`), which is the only code that
  currently implements the cookbook + LLM-fallback pattern.

### 2.4 Key acceptance-criteria facts (per the architect's doc)

- **NetCoreCI**: Windows/Linux .NET CLI/MSBuild/NuGet build; unit tests + **SonarQube
  coverage required**; **SAST/SCA/DAST in parallel** (DAST configurable on/off);
  builds a **Docker image or DLL**, generates an **SBOM**, scans the image, stores in
  **Nexus**, updates the **Helm** chart. Triggers on commit + manual. Dynatrace/Splunk
  wired to the run.
- **NetLegacyCI (.NET FX 4.8)**: **Windows runner**; NuGet/MSBuild/VS Build Tools;
  builds an **MSI installer or DLL** (no container); SBOM + MSI/DLL to **Nexus**.
  Retry ≤ 3 then exception list.
- **PlaywrightCI**: CI for a test repo — **no unit-test / coverage / DAST steps**;
  secret scanning is **blocking**; SCA/SAST non-blocking; produces an SBOM; Node/TS
  test repo → Node image artefact.
- **CD (NetCoreCD / NetLegacyCD)**: generate a **Harness blue/green** pipeline. Reads
  the CI agent's **handoff** (image/registry + tag) rather than re-deriving. **One
  shared Harness template per app-pattern**, held in a **remote Git repo** (not only
  Harness's internal store), **never forked per application**; per-app + per-env config
  supplied separately. Opens one PR; human merges.
- **Orchestrator**: accepts a repo / list / whole git org; classifies into the three
  tech sets and routes to the matching worker; maintains an **exception list** of
  repos it couldn't classify or that a worker failed on; **authors no pipeline itself**.

---

## 3. Repository organization

### 3.1 Production org (the clean, canonical codebases — work here on the work laptop)

> Created as a **separate GitHub organization** so the boundary is unambiguous:
> *in the production org = production code I build on; everything else = history/experiments.*

| Repo | Role |
|------|------|
| `agent-core` | The runtime/framework every agent imports (pinned git dependency). |
| `agent-starter` | The template each new agent repo is stamped from. |
| `cicd-orchestrator` | General-purpose, per-client **classify-and-route** orchestrator (wires to whichever agent services are deployed). |
| `netcore-ci-agent` | .NET Core CI worker — **own cookbook** (.NET Core recipes). |
| `netcore-cd-agent` | .NET Core CD worker (Harness/AKS) — **own cookbook**. |

Future agents are **new repos in this org**: `netlegacy-ci-agent`, `netlegacy-cd-agent`,
`cobol-*-ci/cd-agent`, `playwright-ci-agent`, and the Testing-subsystem agents.

### 3.2 Personal account (`github.com/Komali612`) — left as-is, nothing depends on it at runtime

- `cicd-bootstrap` — **interim cookbook home + best reference** for the cookbook +
  LLM-fallback worker pattern. Cookbook lives at
  `src/cicd_bootstrap/cookbooks/cookbooks.yaml` (CI) and `cd_cookbooks/cd_cookbooks.yaml`.
- `netcore-cicd-agents` — the **demo monorepo** (bundled orchestrator+CI+CD). Source of
  the best current agent code that seeds the production per-agent repos. Not the
  production shape.
- Gen-1/Gen-2 experiments (`ci-agent`, `agentic-cicd`, `agent-contracts`, `ci-authoring`,
  standalone `orchestrator-agent`/`netcore-ci-agent`/`netlegacy-ci-agent`, `ghcr-ci-agent`)
  — superseded; archive candidates. **Note: .NET FX 4.8 capability currently exists ONLY
  in `netlegacy-ci-agent` / `agentic-cicd` — don't lose it.**
- Demo target apps (`netcore-sample-app`, `netcore-ci-demo`, `dotnet-greeting-api`, etc.)
  — throwaway test targets; consolidate to one or two.
- Junk: `.netcore_CICD_agents` (empty), `.netcore-cicd-agents` (accidental dup).

---

## 4. How the pieces interact

```
Developer ─▶ CICD Orchestrator ─(classify repo)─▶ routes to matching agent(s)
                                                       │
   agent: DISCOVER ▶ GENERATE (cookbook→LLM) ▶ VALIDATE (real PR CI run, ≤3 tries) ▶ open PR
                                                       │
   CI agent handoff (image/registry + tag) ───────────┘─▶ CD agent (after CI success)
                                                       │
   Human reviews & MERGES the PR (agent never merges). Failures ▶ exception list.
```
- Every agent depends on **`agent-core`** as a pinned git dependency
  (`agent-core[...] @ git+https://github.com/<ORG>/agent-core@<tag>`). **This URL is
  load-bearing** — if `agent-core` moves orgs, update the pin in every agent's
  `pyproject.toml` in the same change.
- Agents talk over **HTTP**; the orchestrator holds the (per-client) set of agent
  endpoints.
- Observability: **Prometheus/Grafana/Loki/Tempo** on GKE; Dynatrace/Splunk wired to
  CI runs per the acceptance criteria.

---

## 5. Working methodology (rules for every session/agent)

1. **Canonical workspace & Git.** Do all work in the intended repo (per the migration,
   the production-org repos). **Never** work in temporary/scratch directories that then
   only exist on one machine. Everything is tracked in Git with regular commits.
2. **Branches.** Branch off `main` for each piece of work (`feat/…`); commit and push
   regularly; open PRs. Don't commit directly to `main` for non-trivial work.
3. **One repo per agent.** New agent = new repo stamped from `agent-starter`, with its
   **own cookbook** for its framework. Don't bundle agents into a monorepo.
4. **Cookbook placement.** A framework's recipe goes in **that framework's agent repo**
   (interim: `cicd-bootstrap`). Never in the orchestrator or scaffolding.
5. **Agents open PRs, humans merge.** Never auto-merge an agent-generated PR. On
   repeated failure (≤3 tries) escalate to the exception list — no blind retries.
6. **Idempotent generation.** If a pipeline exists, add only what's missing; preserve
   human edits.
7. **Secrets discipline.** Never paste real tokens/credentials into chat. Never send
   secret values through the LLM prompt (the credentialed path is deterministic, not
   LLM). Tokens go only into the local console/CI secret stores. Encrypt secrets at
   rest; fail closed without a key.
8. **`agent-core` version pin is load-bearing** — see §4. Keep tags consistent across
   agents.
9. **Authoritative sources.** Architecture questions are answered from the architect's
   docs (`~/Downloads/Agent_Acceptance_Criteria_v1.1.docx`, `FIG Agentic Flow (1).pdf`)
   and this file — not from possibly-drifted code.

---

## 6. Current state vs. target (known drift to fix)

The demo monorepo `netcore-cicd-agents` implements only a thin slice and diverges from
the authoritative design in three ways — treat these as the backlog:
1. **Orchestrator doesn't classify/route** — it's a UI where the user clicks CI vs CD.
   Target: classify the repo and route automatically.
2. **Workers have no cookbook** — they generate in code. Target: cookbook-first with
   LLM fallback (as `cicd-bootstrap` already does).
3. **.NET Core only** — no NetLegacy, no COBOL, no Testing subsystem yet.

---

## 7. Pointers

- Persistent memory index: `~/.claude/projects/-Users-komalipyla-Desktop-agent/memory/MEMORY.md`
  (see `authoritative-architecture.md`, `workspace-location.md`, `agent-template-system.md`).
- Architect docs: `~/Downloads/Agent_Acceptance_Criteria_v1.1.docx`, `~/Downloads/FIG Agentic Flow (1).pdf`.
