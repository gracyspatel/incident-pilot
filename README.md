# IncidentPilot

An AI agent that investigates production incidents like an on-call engineer would: it gathers evidence from logs,
metrics, deploy history and runbooks, proposes a root cause where every claim is backed by a citation, and waits
for human approval before recommending a fix.

See [`ProjectDetails.md`](ProjectDetails.md) for the full design doc (architecture, components, evaluation plan).

## Status

**Phase 2 — Investigation tools.** See [Build Plan](ProjectDetails.md#13-build-plan-and-milestones).

- [x] Phase 1: repo scaffold + incident simulator (one fault type: `bad_deploy_pool_exhaustion`) + runbooks
- [x] Phase 2: `tools/evidence.py` — shared `EvidenceItem` format returned by every tool below
- [x] Phase 2: `tools/metrics_tool.py` — rolling z-score anomaly detector (built from scratch)
- [x] Phase 2: `tools/log_search.py` — time/service/level/keyword log search
- [x] Phase 2: `tools/deploy_history.py` — deploy lookup + "most recent deploy before time X"
- [x] Phase 2: `tools/runbook_rag.py` — chunk + embed (Sentence Transformers) + retrieve (ChromaDB)
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

## Building the runbook index

The runbook RAG tool needs a ChromaDB collection built from `data/runbooks/` before it can answer queries
(first run downloads the small local embedding model, `all-MiniLM-L6-v2`, ~80MB):

```bash
python -m tools.runbook_rag
```

This writes to `chroma_db/` (gitignored — rebuild it anytime from the committed runbooks).

## Running tests

```bash
pytest
```

The runbook RAG tests load a real embedding model and are noticeably slower (~30-40s) than the rest of the
suite, which runs in under a second.

## Design principles

- **Fundamentals over frameworks**: the simulator, anomaly detector, log search, citation validator, tracer and
  evaluation harness are built from scratch. LangGraph, Groq, Sentence Transformers, ChromaDB, Pydantic and
  Streamlit are used for orchestration, inference, retrieval, schema validation and UI.
- **No citation, no claim**: every claim the agent makes must point to real evidence (a log line ID, metric
  point, deploy record or runbook section).
- **Objective evaluation**: because every fault is planted, the correct answer is always known, so accuracy,
  citation precision and evidence recall are measured, not estimated.
