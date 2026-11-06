"""Fake services that produce *normal* (non-incident) logs and metrics.

Each service has a baseline profile (typical latency, error rate, memory,
and DB connection usage). ``generate_normal_logs`` and ``generate_normal_metrics``
sample around those baselines with a seeded random generator, so the output
looks like noisy-but-stable production telemetry until a fault is injected
on top of it (see faults.py).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from simulator.config import METRIC_INTERVAL_MINUTES, SERVICES


@dataclass
class LogLine:
    """One log line. ``line_id`` is assigned later, once all logs are merged."""

    timestamp: datetime
    service: str
    level: str  # "INFO" | "WARN" | "ERROR"
    message: str
    line_id: str = ""
    # Internal tag used by faults.py to mark lines that are key fault evidence,
    # so generate.py can look up their assigned line_id for the answer key.
    tag: str = ""


@dataclass
class MetricPoint:
    """One row of metrics for one service at one timestamp."""

    timestamp: datetime
    service: str
    latency_ms: float
    error_rate: float
    memory_mb: float
    db_connections: int


@dataclass
class DeployRecord:
    """One deploy event."""

    service: str
    version: str
    timestamp: datetime
    change_notes: str


@dataclass(frozen=True)
class ServiceProfile:
    """Baseline (mean, std) for each metric a service normally produces."""

    latency_mean: float
    latency_std: float
    error_rate_mean: float  # fraction, e.g. 0.005 = 0.5%
    memory_mean: float
    memory_std: float
    db_conn_mean: float
    db_conn_std: float
    log_interval_mean_s: float  # average seconds between log lines
    pool_max: int  # configured DB connection pool size for this service


# [Suggestion] Baseline profiles chosen to be plausible, not measured from a
# real system — this is synthetic data by design (see ProjectDetails.md §7).
SERVICE_PROFILES: dict[str, ServiceProfile] = {
    "web": ServiceProfile(60, 8, 0.005, 300, 15, 0, 0, 6.0, pool_max=0),
    "cart": ServiceProfile(90, 10, 0.005, 350, 20, 5, 1, 8.0, pool_max=20),
    "checkout": ServiceProfile(130, 15, 0.005, 400, 20, 10, 2, 7.0, pool_max=50),
    "db": ServiceProfile(15, 3, 0.002, 800, 40, 40, 5, 5.0, pool_max=200),
    "cache": ServiceProfile(4, 1, 0.001, 200, 10, 0, 0, 4.0, pool_max=0),
}

_INFO_TEMPLATES: dict[str, list[str]] = {
    "web": [
        "GET /home 200 {latency}ms",
        "served static asset in {latency}ms",
        "session {session_id} started",
    ],
    "cart": [
        "added item to cart {session_id} in {latency}ms",
        "cart {session_id} total recalculated",
    ],
    "checkout": [
        "checkout request for order {order_id} handled in {latency}ms",
        "payment authorized for order {order_id}",
    ],
    "db": [
        "query executed in {latency}ms",
        "connection acquired from pool ({used}/{max} in use)",
    ],
    "cache": [
        "cache hit for key {order_id}",
        "cache set for key {order_id}",
    ],
}

_WARN_TEMPLATES: dict[str, list[str]] = {
    "web": ["slow static asset warning, took {latency}ms"],
    "cart": ["cart recalculation took longer than expected ({latency}ms)"],
    "checkout": ["payment provider responded slowly ({latency}ms)"],
    "db": ["query took longer than expected ({latency}ms)"],
    "cache": ["cache eviction rate elevated"],
}

_WARN_PROBABILITY = 0.03


def _fmt(template: str, rng: random.Random, latency: float) -> str:
    return template.format(
        latency=round(latency, 1),
        session_id=f"s{rng.randint(1000, 9999)}",
        order_id=f"o{rng.randint(10000, 99999)}",
        used=rng.randint(1, 10),
        max=50,
    )


def generate_normal_logs(
    rng: random.Random, start: datetime, end: datetime
) -> list[LogLine]:
    """Generate background INFO/WARN logs for every service across the window.

    Each service emits log lines at a random interval around its own
    ``log_interval_mean_s``, independent of the other services.
    """
    logs: list[LogLine] = []
    for service in SERVICES:
        profile = SERVICE_PROFILES[service]
        t = start + timedelta(seconds=rng.uniform(0, profile.log_interval_mean_s))
        while t < end:
            latency = max(0.5, rng.gauss(profile.latency_mean, profile.latency_std))
            is_warn = rng.random() < _WARN_PROBABILITY
            level = "WARN" if is_warn else "INFO"
            templates = _WARN_TEMPLATES[service] if is_warn else _INFO_TEMPLATES[service]
            message = _fmt(rng.choice(templates), rng, latency)
            logs.append(LogLine(timestamp=t, service=service, level=level, message=message))
            t += timedelta(seconds=rng.expovariate(1 / profile.log_interval_mean_s))
    return logs


def generate_normal_metrics(
    rng: random.Random, start: datetime, end: datetime
) -> list[MetricPoint]:
    """Generate one metrics row per service per METRIC_INTERVAL_MINUTES."""
    points: list[MetricPoint] = []
    t = start
    while t < end:
        for service in SERVICES:
            profile = SERVICE_PROFILES[service]
            points.append(
                MetricPoint(
                    timestamp=t,
                    service=service,
                    latency_ms=round(max(0.5, rng.gauss(profile.latency_mean, profile.latency_std)), 2),
                    error_rate=round(max(0.0, rng.gauss(profile.error_rate_mean, profile.error_rate_mean / 2 or 0.001)), 4),
                    memory_mb=round(max(10.0, rng.gauss(profile.memory_mean, profile.memory_std)), 1),
                    db_connections=max(0, round(rng.gauss(profile.db_conn_mean, profile.db_conn_std))),
                )
            )
        t += timedelta(minutes=METRIC_INTERVAL_MINUTES)
    return points


def generate_background_deploys(
    rng: random.Random, start: datetime, end: datetime, before: datetime
) -> list[DeployRecord]:
    """Generate a couple of harmless deploys before ``before`` (the fault deploy)."""
    deploys: list[DeployRecord] = []
    candidates = [s for s in SERVICES if s not in ("db",)]
    rng.shuffle(candidates)
    for service in candidates[:2]:
        offset = rng.uniform(0, max(1.0, (before - start).total_seconds() - 60))
        t = start + timedelta(seconds=offset)
        version = f"v{rng.randint(1, 3)}.{rng.randint(0, 9)}.{rng.randint(0, 9)}"
        deploys.append(
            DeployRecord(
                service=service,
                version=version,
                timestamp=t,
                change_notes=f"Routine release of {service} {version} (no functional change).",
            )
        )
    deploys.sort(key=lambda d: d.timestamp)
    return deploys
