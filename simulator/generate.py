"""Builds a complete incident folder: normal telemetry + one injected fault.

Usage:
    python -m simulator.generate
    python -m simulator.generate --incident-id inc_002 --seed 7

Output (data/incidents/<incident_id>/, gitignored — reproducible from the seed):
    logs.jsonl       one JSON object per log line, sorted by time, unique line_id
    metrics.csv      one row per (timestamp, service)
    deploys.json     deploy history, sorted by time
    answer_key.json  hidden ground truth: root cause, fault start, key evidence IDs
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

from simulator.config import DEFAULT_SEED, SIM_DURATION_MINUTES, SIM_START
from simulator.faults import FaultInfo, inject_bad_deploy_pool_exhaustion
from simulator.services import (
    DeployRecord,
    LogLine,
    MetricPoint,
    generate_background_deploys,
    generate_normal_logs,
    generate_normal_metrics,
)

DATA_ROOT = Path(__file__).resolve().parent.parent / "data" / "incidents"


def _assign_line_ids(logs: list[LogLine]) -> None:
    """Sort logs by time and assign sequential, unique line IDs in place."""
    logs.sort(key=lambda line: line.timestamp)
    for i, line in enumerate(logs, start=1):
        line.line_id = f"L{i:06d}"


def _write_logs(path: Path, logs: list[LogLine]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for line in logs:
            row = {
                "line_id": line.line_id,
                "timestamp": line.timestamp.isoformat(),
                "service": line.service,
                "level": line.level,
                "message": line.message,
            }
            f.write(json.dumps(row) + "\n")


def _write_metrics(path: Path, metrics: list[MetricPoint]) -> None:
    metrics = sorted(metrics, key=lambda m: (m.timestamp, m.service))
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "service", "latency_ms", "error_rate", "memory_mb", "db_connections"])
        for m in metrics:
            writer.writerow([m.timestamp.isoformat(), m.service, m.latency_ms, m.error_rate, m.memory_mb, m.db_connections])


def _write_deploys(path: Path, deploys: list[DeployRecord]) -> None:
    rows = [
        {
            "service": d.service,
            "version": d.version,
            "timestamp": d.timestamp.isoformat(),
            "change_notes": d.change_notes,
        }
        for d in sorted(deploys, key=lambda d: d.timestamp)
    ]
    path.write_text(json.dumps(rows, indent=2), encoding="utf-8")


def _build_answer_key(incident_id: str, seed: int, fault: FaultInfo) -> dict:
    key_evidence = [f"deploy:{fault.root_cause_service}:{fault.deploy_record.version}"]
    key_evidence += [f"log:{fault.root_cause_service}:{line.line_id}" for line in fault.key_log_lines]
    key_evidence += [
        f"metric:{fault.root_cause_service}.latency_ms",
        f"metric:{fault.root_cause_service}.db_connections",
    ]
    return {
        "incident_id": incident_id,
        "seed": seed,
        "fault_type": fault.fault_type,
        "root_cause_service": fault.root_cause_service,
        "root_cause_change": fault.root_cause_change,
        "deploy_time": fault.deploy_time.isoformat(),
        "fault_start": fault.fault_start.isoformat(),
        "old_pool_size": fault.old_pool_size,
        "new_pool_size": fault.new_pool_size,
        "key_evidence": key_evidence,
        "distractors": [],
    }


def generate_incident(
    seed: int = DEFAULT_SEED, incident_id: str = "inc_001", output_root: Path | None = None
) -> Path:
    """Generate one incident and write it to ``output_root``/<incident_id>/.

    Deterministic: the same seed always produces byte-identical output, which
    is why the default output directory (data/incidents/) is gitignored rather
    than committed. ``output_root`` is overridable so tests can target a
    temporary directory instead.
    """
    rng = random.Random(seed)
    sim_end = SIM_START + timedelta(minutes=SIM_DURATION_MINUTES)

    logs = generate_normal_logs(rng, SIM_START, sim_end)
    metrics = generate_normal_metrics(rng, SIM_START, sim_end)

    deploy_offset = rng.randint(50, 70)  # minutes into the window
    deploy_time = SIM_START + timedelta(minutes=deploy_offset)
    fault_start = deploy_time + timedelta(minutes=rng.randint(1, 3))

    deploys = generate_background_deploys(rng, SIM_START, sim_end, before=deploy_time)

    fault = inject_bad_deploy_pool_exhaustion(
        rng, metrics, logs, deploys, deploy_time=deploy_time, fault_start=fault_start, sim_end=sim_end
    )

    _assign_line_ids(logs)

    out_dir = (output_root or DATA_ROOT) / incident_id
    out_dir.mkdir(parents=True, exist_ok=True)

    _write_logs(out_dir / "logs.jsonl", logs)
    _write_metrics(out_dir / "metrics.csv", metrics)
    _write_deploys(out_dir / "deploys.json", deploys)

    answer_key = _build_answer_key(incident_id, seed, fault)
    (out_dir / "answer_key.json").write_text(json.dumps(answer_key, indent=2), encoding="utf-8")

    return out_dir


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Generate a synthetic incident.")
    parser.add_argument("--incident-id", default="inc_001")
    parser.add_argument("--seed", type=int, default=int(os.getenv("SIMULATOR_SEED", DEFAULT_SEED)))
    args = parser.parse_args()

    out_dir = generate_incident(seed=args.seed, incident_id=args.incident_id)
    print(f"Generated incident '{args.incident_id}' (seed={args.seed}) -> {out_dir}")


if __name__ == "__main__":
    main()
