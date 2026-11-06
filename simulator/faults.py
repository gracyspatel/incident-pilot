"""Fault injection: mutates normal telemetry to simulate a real incident.

Phase 1 implements exactly one fault type, matching ProjectDetails.md §7:

    "bad deploy shrinks the DB connection pool" ->
        pool-exhausted errors + a latency spike on the affected service,
        starting shortly after a deploy that reduced the pool size.

More fault types (memory leak, dependency outage, disk full, cache
failure) are listed in the design doc for later phases but are out of
scope here — Phase 1 is deliberately narrow (see README "Status").
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta

from simulator.services import DeployRecord, LogLine, MetricPoint, SERVICE_PROFILES

FAULT_TYPE = "bad_deploy_pool_exhaustion"
FAULT_SERVICE = "checkout"

# How many minutes after the fault starts the error rate/latency fully ramps
# up to its plateau, rather than jumping instantly (slightly more realistic).
_RAMP_MINUTES = 10


@dataclass
class FaultInfo:
    """Ground-truth facts about the injected fault, used to build the answer key."""

    fault_type: str
    root_cause_service: str
    root_cause_change: str
    deploy_time: datetime
    fault_start: datetime
    old_pool_size: int
    new_pool_size: int
    deploy_record: DeployRecord
    key_log_lines: list[LogLine]


def inject_bad_deploy_pool_exhaustion(
    rng: random.Random,
    metrics: list[MetricPoint],
    logs: list[LogLine],
    deploys: list[DeployRecord],
    deploy_time: datetime,
    fault_start: datetime,
    sim_end: datetime,
) -> FaultInfo:
    """Mutate ``metrics``, ``logs`` and ``deploys`` in place to inject the fault.

    ``deploy_time`` and ``fault_start`` are decided by the caller (generate.py),
    which owns the overall incident timeline; this function only knows how to
    mutate telemetry given those two timestamps.

    Returns a FaultInfo describing exactly what was injected and when, which
    generate.py uses to build the hidden answer_key.json.
    """
    service = FAULT_SERVICE
    profile = SERVICE_PROFILES[service]

    old_pool = profile.pool_max
    new_pool = rng.randint(3, 6)
    version = f"v{rng.randint(2, 4)}.{rng.randint(0, 9)}.{rng.randint(0, 9)}"
    change_notes = (
        f"Reduced {service}_db_pool size from {old_pool} to {new_pool} "
        "connections to cut database costs."
    )
    deploy_record = DeployRecord(
        service=service, version=version, timestamp=deploy_time, change_notes=change_notes
    )
    deploys.append(deploy_record)
    deploys.sort(key=lambda d: d.timestamp)

    _mutate_metrics(rng, metrics, service, fault_start, sim_end, new_pool)
    key_log_lines = _inject_error_logs(rng, logs, service, fault_start, sim_end, new_pool)

    return FaultInfo(
        fault_type=FAULT_TYPE,
        root_cause_service=service,
        root_cause_change=f"deploy {service} {version}",
        deploy_time=deploy_time,
        fault_start=fault_start,
        old_pool_size=old_pool,
        new_pool_size=new_pool,
        deploy_record=deploy_record,
        key_log_lines=key_log_lines,
    )


def _ramp_factor(t: datetime, fault_start: datetime) -> float:
    """0 right at fault_start, ramps linearly to 1 over _RAMP_MINUTES, then stays at 1."""
    elapsed_min = (t - fault_start).total_seconds() / 60
    return min(1.0, max(0.0, elapsed_min / _RAMP_MINUTES))


def _mutate_metrics(
    rng: random.Random,
    metrics: list[MetricPoint],
    service: str,
    fault_start: datetime,
    sim_end: datetime,
    new_pool: int,
) -> None:
    profile = SERVICE_PROFILES[service]
    for point in metrics:
        if point.service != service or point.timestamp < fault_start:
            continue
        ramp = _ramp_factor(point.timestamp, fault_start)
        # Requests queue waiting for a free connection: latency climbs sharply.
        latency_multiplier = 1 + ramp * rng.uniform(10, 16)
        point.latency_ms = round(profile.latency_mean * latency_multiplier, 2)
        # A large share of requests fail outright once the pool is saturated.
        point.error_rate = round(min(0.9, ramp * rng.uniform(0.35, 0.6)), 4)
        # Connections in use are capped at the new, smaller pool size.
        point.db_connections = max(1, min(new_pool, round(new_pool - rng.uniform(0, 0.5))))


def _inject_error_logs(
    rng: random.Random,
    logs: list[LogLine],
    service: str,
    fault_start: datetime,
    sim_end: datetime,
    new_pool: int,
) -> list[LogLine]:
    key_log_lines: list[LogLine] = []
    t = fault_start
    while t < sim_end:
        ramp = _ramp_factor(t, fault_start)
        # Errors start sparse and ramp up to frequent as the ramp progresses.
        mean_interval_s = max(1.5, 15 - ramp * 12)
        wait_ms = round(rng.uniform(500, 3000) * (1 + ramp), 1)
        message = (
            f"pool exhausted: could not obtain connection from pool "
            f"({service}_db_pool, size={new_pool}) after waiting {wait_ms}ms"
        )
        line = LogLine(
            timestamp=t,
            service=service,
            level="ERROR",
            message=message,
            tag="pool_exhausted",
        )
        logs.append(line)
        if len(key_log_lines) < 3:
            key_log_lines.append(line)
        t += timedelta(seconds=rng.expovariate(1 / mean_interval_s))
    return key_log_lines
