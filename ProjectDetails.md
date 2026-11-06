# IncidentPilot — Project Explainer

> An AI agent that investigates production incidents like an on-call engineer would: it gathers evidence from logs, metrics, deploy history and runbooks, proposes a root cause where every claim is backed by a citation, and waits for human approval before recommending a fix.

**Author:** Gracy (Grace) Patel
**Status:** Planning
**Labels used in this doc:** **[Fact]** = verified or standard practice · **[Suggestion]** = design choice proposed for this project · **[Assumption]** = something to confirm before building

---

## Table of Contents

1. [The Story (Intuition First)](#1-the-story-intuition-first)
2. [The Problem](#2-the-problem)
3. [What IncidentPilot Does](#3-what-incidentpilot-does)
4. [Glossary](#4-glossary)
5. [System Architecture](#5-system-architecture)
6. [Component Deep Dive](#6-component-deep-dive)
7. [The Incident Simulator (Where the Data Comes From)](#7-the-incident-simulator-where-the-data-comes-from)
8. [Evaluation](#8-evaluation)
9. [Worked Example: One Incident End to End](#9-worked-example-one-incident-end-to-end)
10. [Tech Stack and Why](#10-tech-stack-and-why)
11. [What I Build Myself vs. What Uses Libraries](#11-what-i-build-myself-vs-what-uses-libraries)
12. [Proposed Folder Structure](#12-proposed-folder-structure)
13. [Build Plan and Milestones](#13-build-plan-and-milestones)
14. [Limitations (Say These Honestly)](#14-limitations-say-these-honestly)
15. [Interview Prep: Questions I Should Be Ready For](#15-interview-prep-questions-i-should-be-ready-for)
16. [Resume Bullet Template](#16-resume-bullet-template)
17. [Open Questions Before Building](#17-open-questions-before-building)
18. [References](#18-references)

---

## 1. The Story (Intuition First)

It is 3 a.m. Priya is the **on-call engineer** for an online store. Her phone buzzes:

> 🚨 *"Checkout is slow — 40% of payments are timing out."*

Something in **production** (the live system real customers use) is broken. This is an **incident**. Priya now becomes a detective:

| Step | What Priya does | What she finds |
|---|---|---|
| 1 | Opens the **metrics** dashboard | Latency jumped at 2:47 a.m. |
| 2 | Searches the **logs** | Thousands of `database connection pool exhausted` errors |
| 3 | Checks **deploy history** | New code version released at 2:45 a.m. |
| 4 | Reads the **runbook** | "Pool exhausted after a deploy → roll back" |
| 5 | Rolls back, then writes a **postmortem** | Root cause: the new deploy shrank the DB pool size |

This takes a tired human a long time because the evidence is spread across many tools.

**IncidentPilot does the detective work.** It collects the evidence, connects the dots, explains the root cause with proof, and asks Priya to approve the fix. She stays in control; the agent does the searching.

---

## 2. The Problem

- **Evidence is scattered.** Logs, metrics, deploy history and documentation live in separate tools.
- **Investigations are slow under pressure.** On-call engineers are often tired and context-switching.
- **AI answers can't be trusted blindly.** An LLM that "guesses" a root cause without evidence is dangerous in production.

**Goal:** an agent that is *useful* (finds the cause quickly) and *trustworthy* (every claim is backed by real evidence, and a human approves actions).

**Intended users:** on-call engineers, SREs (Site Reliability Engineers), DevOps and backend teams.

---

## 3. What IncidentPilot Does

**Input**
- A symptom/alert (e.g., "cart service restarting repeatedly")
- Access to: logs, metrics, deploy history, runbooks

**Output** — a structured report:
- Root cause (one clear sentence)
- Evidence list (each item = a specific log line, metric point, deploy record or runbook section)
- Timeline of events
- Recommended fix (only after human approval)
- Prevention suggestions
- A full **execution trace** of every step the agent took

**Core rule:** *No citation, no claim.* If the agent cannot point to real evidence, the claim is rejected.

---

## 4. Glossary

| Term | Plain-English meaning |
|---|---|
| **Production** | The live system real users interact with |
| **Incident** | An event where production is broken or degraded |
| **On-call engineer** | The person responsible for responding to incidents during a shift |
| **Alert** | An automatic notification that something crossed a threshold |
| **Logs** | Timestamped text lines software writes while running (e.g., errors, requests) |
| **Metrics** | Numbers tracked over time (latency, error rate, memory usage) |
| **Deploy** | Releasing a new version of code to production |
| **Rollback** | Reverting to the previous working version |
| **Runbook** | A team's step-by-step guide for handling known problems |
| **Postmortem** | A report written after an incident: what happened, why, and how to prevent it |
| **Root cause** | The underlying reason the incident happened (not just the symptom) |
| **Anomaly detection** | Automatically spotting unusual behavior in a metric |
| **z-score** | How many standard deviations a value is from the mean: `z = (x − μ) / σ` |
| **RAG** | Retrieval-Augmented Generation: fetch relevant documents first, then let the LLM answer using them |
| **Embedding** | A vector (list of numbers) representing text meaning, so similar text ends up close together |
| **Citation grounding** | Every claim in the output must point to real source evidence |
| **Structured output** | LLM output forced into a fixed schema (e.g., JSON validated by Pydantic) |
| **Human-in-the-loop (HITL)** | The system pauses and waits for a human to approve before continuing |
| **Execution trace** | A record of every step: which tool, what input, what output, how long it took |
| **Cost-aware routing** | Using cheaper models for simple steps and stronger models only where needed |
| **Distractor** | A deliberately planted, unrelated error meant to mislead the investigation |

---

## 5. System Architecture

```
            ┌──────────────────────────────┐
            │  Alert: "checkout is slow"   │
            └──────────────┬───────────────┘
                           │
                   ┌───────▼────────┐
                   │ Planner Agent  │  Decomposes into investigation steps
                   └───────┬────────┘
                           │
    ┌──────────────┬───────┴───────┬────────────────┐
    │              │               │                │
┌───▼────┐   ┌─────▼─────┐   ┌─────▼──────┐   ┌─────▼──────┐
│Metrics │   │ Log Search│   │  Deploy    │   │ Runbook    │
│ Tool   │   │   Tool    │   │  History   │   │ RAG Tool   │
│(anomaly│   │(time +    │   │   Tool     │   │ (ChromaDB) │
│ detect)│   │ keyword)  │   │            │   │            │
└───┬────┘   └─────┬─────┘   └─────┬──────┘   └─────┬──────┘
    └──────────────┴───────┬───────┴────────────────┘
                           │  evidence items (E1, E2, ...)
                   ┌───────▼────────┐
                   │ Analyst Agent  │  Forms hypothesis, links claims → evidence
                   └───────┬────────┘
                           │
                   ┌───────▼────────┐
                   │   Validator    │  Rejects claims with missing/fake citations
                   └───────┬────────┘
                           │
                   ┌───────▼────────┐
                   │ Human Approval │  Approve / reject proposed fix
                   └───────┬────────┘
                           │
                   ┌───────▼────────┐
                   │ Report + Trace │  Saved to SQLite, shown in Streamlit
                   └────────────────┘
```

---

## 6. Component Deep Dive

### 6.1 Planner Agent
- **What:** turns the alert into an ordered list of investigation steps.
- **Why it's needed:** without a plan, the agent calls tools randomly and wastes time/cost.
- **Output (structured):** `["check_metrics(service=cart)", "search_logs(window=14:30-15:30)", "check_deploys()", "query_runbook(symptom)"]`

### 6.2 Metrics Tool (Anomaly Detection) — *built by me*
- **What:** finds where a metric started behaving abnormally.
- **How (simplest version):** rolling z-score. For each point `x`, compute mean `μ` and std `σ` over a recent window; flag if `|z| > 3`.
- **Why z-score first:** easy to explain and debug. Can be upgraded later (e.g., seasonal baselines).
- **Returns:** anomaly start time, metric name, values → becomes an evidence item.

### 6.3 Log Search Tool — *built by me*
- **What:** searches logs by time window, service and keywords/error level.
- **Returns:** matching lines with line IDs, counts and first/last occurrence → evidence items.
- **Why line IDs matter:** the validator needs exact IDs to verify citations.

### 6.4 Deploy History Tool
- **What:** lists what changed and when (service, version, timestamp, change notes).
- **Why:** many real incidents follow a change; correlating timing is a key clue.

### 6.5 Runbook RAG Tool
- **What:** retrieves the most relevant runbook sections for the symptom.
- **How:** runbooks are chunked → embedded with Sentence Transformers → stored in ChromaDB → top-k retrieval.
- **Returns:** section text + source ID → evidence items.

### 6.6 Analyst Agent
- **What:** reads all evidence and writes a hypothesis where every sentence cites evidence IDs.
- **Output schema (Pydantic, [Suggestion]):**

```python
class Claim(BaseModel):
    text: str
    evidence_ids: list[str]   # must be non-empty

class InvestigationReport(BaseModel):
    root_cause: Claim
    timeline: list[Claim]
    recommended_fix: Claim
    prevention: list[str]
    confidence: Literal["low", "medium", "high"]
```

### 6.7 Validator — *built by me*
- **Checks:**
  1. Every claim has at least one evidence ID.
  2. Every cited ID actually exists in the collected evidence.
  3. Timestamps are consistent (e.g., the cause can't happen after the symptom).
- **On failure:** sends the report back to the Analyst with the error, or marks the claim "unsupported."

### 6.8 Human Approval
- **What:** the graph pauses before recommending/finalizing a fix; the user approves, edits or rejects.
- **How:** LangGraph's `interrupt` pauses execution, and the graph resumes with `Command(resume=...)` carrying the human's input. **[Fact — LangGraph docs]**

### 6.9 Observability (Tracing) — *built by me*
- **What:** logs every step to SQLite: step name, tool, input, output summary, latency, tokens, model used, cost.
- **Why:** debugging, cost analysis and a great interview demo ("here is exactly what the agent did").

### 6.10 Cost-Aware Routing
- **What:** a small/fast model for simple tasks (summarizing log chunks), a stronger model for final reasoning.
- **Rule:** only claim this as a feature if I **measure** cost and accuracy with vs. without routing.

---

## 7. The Incident Simulator (Where the Data Comes From)

Real company logs are private, so I generate realistic **synthetic** incidents. This is the key design decision of the project.

### How it works
1. **Simulate a small fake system:** e.g., `web`, `cart`, `checkout`, `db`, `cache` services producing normal logs and metrics.
2. **Inject one known fault** at a chosen time.
3. **Optionally add distractors:** unrelated warnings or noise to make the investigation harder.
4. **Save an answer key** (hidden from the agent).

### Example fault types **[Suggestion]**

| Fault | What changes in the data | Correct root cause |
|---|---|---|
| Bad deploy shrinks DB pool | Deploy record + `pool exhausted` errors + latency spike | Deploy vX changed pool config |
| Memory leak | Memory climbs steadily + `OutOfMemoryError` + restarts | Leak introduced in deploy vX |
| Downstream dependency down | Timeout errors calling `payment-api` | External dependency outage |
| Disk full | Write errors + disk usage at 100% | Disk exhaustion on host Y |
| Cache failure | Cache miss rate jumps + DB load rises | Cache node failure |

### Answer key format

```json
{
  "incident_id": "inc_007",
  "fault_type": "memory_leak",
  "root_cause_service": "cart",
  "root_cause_change": "deploy cart v4.1.0",
  "fault_start": "14:45",
  "key_evidence": ["log:cart:OutOfMemoryError", "metric:cart.memory", "deploy:cart:v4.1.0"],
  "distractors": ["log:web:slow_static_asset_warning"]
}
```

---

## 8. Evaluation

Because I planted every fault, **I always know the correct answer**. That makes evaluation objective.

| Metric | Definition | Why it matters |
|---|---|---|
| **Root-cause accuracy** | % of incidents where the agent identifies the correct cause | Is it actually useful? |
| **Citation precision** | % of cited evidence items that truly support the claim | Is it trustworthy? |
| **Evidence recall** | % of the answer key's key evidence the agent found | Did it look in the right places? |
| **Distractor robustness** | Accuracy on incidents with vs. without distractors | Does it get fooled? |
| **Steps / tool calls** | Average number of tool calls per investigation | Is it efficient? |
| **Latency** | Time per investigation | Is it fast enough? |
| **Cost** | Tokens/cost per investigation, with vs. without routing | Is routing worth it? |

### Baselines to compare against **[Suggestion]**
1. **Single LLM call:** dump all evidence into one prompt, ask for the root cause.
2. **Agent without validator:** same agent, no citation checking.
3. **Full IncidentPilot.**

This comparison shows *why* each component exists — strong material for interviews.

**Rule:** report only measured numbers. No invented metrics.

---

## 9. Worked Example: One Incident End to End

**Injected fault:** at 14:45, deploy `cart v4.1.0` introduces a memory leak.
**Distractor:** a harmless `slow static asset` warning on the `web` service.

| # | Step | Result |
|---|---|---|
| 1 | Alert arrives | "cart service restarting repeatedly" |
| 2 | Planner | `[check memory metrics, search cart logs 14:30–15:30, check deploys, query runbook]` |
| 3 | Metrics tool | Memory rises from 14:45; z-score > 3 at 15:05 → **E1** |
| 4 | Log search | `OutOfMemoryError` × many, first at 15:06 → **E2** |
| 5 | Deploy history | `cart v4.1.0 @ 14:44` → **E3** |
| 6 | Runbook RAG | "Memory growth after deploy → suspect leak; roll back" → **E4** |
| 7 | Analyst | "Root cause: memory leak introduced in cart v4.1.0 [E1, E2, E3]. Fix: roll back to v4.0.9 [E4]." Ignores the distractor. |
| 8 | Validator | All IDs exist; deploy (14:44) precedes anomaly (15:05) ✅ |
| 9 | Human approval | User approves the rollback recommendation |
| 10 | Scoring | Matches answer key → **correct**; distractor not cited ✅ |

---

## 10. Tech Stack and Why

| Tool | Role | Why this choice |
|---|---|---|
| **Python 3.11+** | Core language | Standard for ML/AI engineering |
| **LangGraph** | Agent orchestration | Graph-based control flow + built-in human-in-the-loop interrupts |
| **Groq** | LLM inference | Fast inference, low cost [Assumption: confirm current pricing/limits] |
| **Sentence Transformers** | Local embeddings | Free, runs locally, no API cost |
| **ChromaDB** | Vector store | Simple local vector DB for runbook retrieval |
| **Pydantic** | Structured output validation | Enforces schemas; catches malformed LLM output |
| **SQLite** | Trace storage | Zero-setup database for execution traces |
| **Streamlit** | UI | Fast way to build an interactive demo |
| **Pytest** | Testing | Unit tests for tools, validator and simulator |

**Security rules:** API keys in `.env` (never committed), `.env.example` checked in, no secrets in code.

---

## 11. What I Build Myself vs. What Uses Libraries

This keeps the project aligned with my **"fundamentals over frameworks"** portfolio theme.

| Built from scratch (I can explain every line) | Library-provided |
|---|---|
| Incident simulator + fault injector | Agent graph orchestration (LangGraph) |
| Anomaly detector (rolling z-score) | Embeddings (Sentence Transformers) |
| Log search tool | Vector store (ChromaDB) |
| Citation validator | LLM API calls (Groq) |
| Tracing/observability layer | UI (Streamlit) |
| Evaluation harness + metrics | Schema validation engine (Pydantic) |

---

## 12. Proposed Folder Structure

**[Suggestion]**

```
incidentpilot/
├── README.md
├── requirements.txt
├── .env.example
├── simulator/
│   ├── services.py          # fake services producing normal logs/metrics
│   ├── faults.py            # fault injection (leak, bad deploy, ...)
│   ├── distractors.py       # unrelated noise
│   └── generate.py          # builds incident folders + answer keys
├── data/
│   ├── incidents/           # generated incidents (logs, metrics, deploys)
│   └── runbooks/            # markdown runbooks
├── tools/
│   ├── metrics_tool.py      # z-score anomaly detection
│   ├── log_search.py
│   ├── deploy_history.py
│   └── runbook_rag.py
├── agent/
│   ├── schemas.py           # Pydantic models
│   ├── planner.py
│   ├── analyst.py
│   ├── validator.py
│   ├── router.py            # cost-aware model selection
│   └── graph.py             # LangGraph wiring + HITL interrupt
├── observability/
│   └── tracer.py            # SQLite trace logging
├── eval/
│   ├── run_eval.py          # runs agent on all incidents
│   ├── metrics.py           # accuracy, citation precision, ...
│   └── baselines.py         # single-call LLM, no-validator agent
├── app/
│   └── streamlit_app.py
└── tests/
    ├── test_simulator.py
    ├── test_tools.py
    └── test_validator.py
```

---

## 13. Build Plan and Milestones

| Phase | Goal | Done when |
|---|---|---|
| **Day 1 — MVP** | One fault type (bad deploy) end to end | Agent finds the cause on 1 simulated incident with citations |
| **Days 2–3 — Simulator** | 5 fault types + distractors + answer keys | `generate.py` creates 20–30 incidents reproducibly |
| **Days 4–5 — Agent quality** | Validator, HITL, tracing, routing | Unsupported claims get rejected; traces saved |
| **Days 6–7 — Evaluation** | Run all incidents + baselines | Results table with real numbers |
| **Day 8 — UI** | Streamlit dashboard | Alert → investigation → approval → report → trace view |
| **Days 9–10 — Polish** | README, architecture diagram, demo video, tests | Repo is presentable; tests pass |

**Realistic expectation:** ~1 day for a demo, ~1–2 weeks for a resume-quality version.

---

## 14. Limitations (Say These Honestly)

- **Synthetic data is simpler than real incidents.** Mitigation: distractors, multiple overlapping signals, varied fault types.
- **One root cause per incident.** Real incidents can have multiple contributing causes (possible extension).
- **The LLM may still reason incorrectly** even with correct evidence; the validator checks citations exist, not that reasoning is perfect.
- **Not production-integrated.** It reads files, not live Datadog/Prometheus systems (possible extension).
- **Prior work:** commercial AIOps / "AI SRE" tools likely exist **[Assumption — not yet checked]**. Present this as an engineering + evaluation project, not a new invention.

---

## 15. Interview Prep: Questions I Should Be Ready For

1. **Why an agent instead of one LLM call?** → Compare against the single-call baseline; show the accuracy/citation difference.
2. **How do you prevent hallucinations?** → Citation-required schema + validator that checks evidence IDs exist and timestamps are consistent.
3. **Why synthetic data? Isn't that cheating?** → Real logs are private; synthetic data gives ground truth for objective evaluation. Explain distractors.
4. **Why z-score for anomaly detection?** → Simple, explainable baseline; know its weakness (assumes roughly stable mean/variance, struggles with seasonality).
5. **Why human-in-the-loop?** → Fixes in production are high-risk; humans approve actions, the agent gathers evidence.
6. **What does cost-aware routing save?** → Only answer with measured numbers.
7. **How would this work in a real company?** → Replace file-based tools with connectors to log/metric systems; same agent logic.
8. **What failed during development?** → Keep a log of real failures while building — interviewers love this question.

---

## 16. Resume Bullet Template

*(Fill X, Y, N, Z only with real measured results.)*

> - Built **IncidentPilot**, a LangGraph-based multi-tool agent that investigates production incidents across logs, metrics, deploy history and runbooks, producing citation-grounded root-cause reports with human-in-the-loop approval.
> - Designed a fault-injection simulator generating **N** incidents with ground-truth root causes and distractors; agent achieved **X%** root-cause accuracy and **Y%** citation precision vs. **Z%** for a single-call LLM baseline.
> - Implemented from scratch a rolling z-score anomaly detector, citation validator and SQLite execution tracer for auditable, debuggable investigations.

---

## 17. Open Questions Before Building

- [ ] Solo project or team?
- [ ] How many days/weeks can I commit?
- [ ] Groq free-tier limits enough for ~30 incidents × 3 baselines? (check current limits)
- [ ] Which 3 fault types to start with?
- [ ] Do I want a live demo deployed (e.g., Streamlit Cloud) or just a demo video?

---

## 18. References

- LangGraph — Human-in-the-loop (interrupts): https://docs.langchain.com/oss/python/langgraph/add-human-in-the-loop
- *(More references — Pydantic, ChromaDB, Sentence Transformers, Groq docs, SRE postmortem practices — to be added after verification.)*