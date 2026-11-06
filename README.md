# IncidentPilot

An AI agent that investigates production incidents like an on-call engineer would: it gathers evidence from logs,
metrics, deploy history and runbooks, proposes a root cause where every claim is backed by a citation, and waits
for human approval before recommending a fix.

See [`ProjectDetails.md`](ProjectDetails.md) for the full design doc (architecture, components, evaluation plan).

## Status

**Phase 1 — Repo setup + incident simulator (one fault type).** See [Build Plan](ProjectDetails.md#13-build-plan-and-milestones).

- [x] Repo scaffold, `.gitignore`, `requirements.txt`, `.env.example`
- [x] Simulator: normal logs/metrics for a 5-service fake system + one injected fault
      (`bad_deploy_pool_exhaustion`) + answer key
- [x] Runbooks (`data/runbooks/`)
- [x] Tests for the simulator
- [ ] Phase 2: metrics anomaly detector, log search, deploy history, runbook RAG tools
- [ ] Phase 3: agent graph (planner, analyst, validator, human-in-the-loop)
- [ ] Phase 4: observability tracer + cost-aware routing
- [ ] Phase 5: evaluation harness + baselines
- [ ] Phase 6: Streamlit UI

## Project structure

```
incidentpilot/
├── simulator/       # fake services, fault injection, incident generation
├── data/
│   ├── incidents/   # generated incidents (gitignored — reproducible from a seed)
│   └── runbooks/    # markdown runbooks (committed)
├── tools/           # metrics/log/deploy/runbook tools used by the agent
├── agent/           # LangGraph planner/analyst/validator wiring
├── observability/   # SQLite execution tracer
├── eval/            # evaluation harness + baselines
├── app/             # Streamlit UI
└── tests/           # pytest suite
```

## Setup

Requires Python 3.11+ (tested on 3.13).

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
copy .env.example .env        # then fill in GROQ_API_KEY when Phase 3 needs it
```

## Running the simulator

Generates one incident (normal logs/metrics + an injected "bad deploy shrinks the DB connection pool" fault)
into `data/incidents/<incident_id>/`:

```bash
python -m simulator.generate
```

Each run is deterministic given the same seed (`SIMULATOR_SEED` in `.env`, default 42), so the output is
reproducible without being committed to git.

## Running tests

```bash
pytest
```

## Design principles

- **Fundamentals over frameworks**: the simulator, anomaly detector, log search, citation validator, tracer and
  evaluation harness are built from scratch. LangGraph, Groq, Sentence Transformers, ChromaDB, Pydantic and
  Streamlit are used for orchestration, inference, retrieval, schema validation and UI.
- **No citation, no claim**: every claim the agent makes must point to real evidence (a log line ID, metric
  point, deploy record or runbook section).
- **Objective evaluation**: because every fault is planted, the correct answer is always known, so accuracy,
  citation precision and evidence recall are measured, not estimated.
