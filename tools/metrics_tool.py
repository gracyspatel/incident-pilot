"""Metrics anomaly detection via rolling z-score — built from scratch.

No statistics library (no scipy/statsmodels) is used for the detection
itself: mean, variance and z-score are computed with plain Python so every
step is explainable. See ProjectDetails.md §6.2.

For each point, the mean/std of the preceding ``window`` points is
computed, and the point is flagged as anomalous if its z-score magnitude
exceeds ``threshold``. Using only *preceding* points (not a centered
window) matters: it mirrors how this would run in production, where you
only ever know the past, not the future.

Known blind spot (found while testing against simulated data, not a bug):
a metric that steps instantly to a new, low-noise constant (e.g. a
connection count pinned at a newly-reduced pool size) is only detectable
for the single point where the window is still "clean" — a few points
later the window has re-baselined around the new constant and z collapses
back toward 0. Requiring a short streak of consecutive anomalous points
(``min_consecutive``) to avoid flagging one-off noise blips means this
kind of step change often won't qualify. This is expected, not something
to tune away: it's one reason the agent uses multiple tools (log search
and deploy history catch this kind of fault just fine) instead of relying
on any single detector.
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from tools.evidence import EvidenceItem

DEFAULT_WINDOW = 10
DEFAULT_THRESHOLD = 3.0
DEFAULT_METRIC_NAMES = ["latency_ms", "error_rate", "memory_mb", "db_connections"]

# Below this, a standard deviation is treated as "effectively zero" to avoid
# dividing by (near-)zero on a perfectly flat window.
_STD_EPSILON = 1e-9


def rolling_zscore(values: list[float], window: int = DEFAULT_WINDOW) -> list[float | None]:
    """Z-score of each point against the mean/std of the ``window`` points before it.

    The first ``window`` points get ``None`` — there isn't enough history yet
    to judge them. z = (x - mean) / std, computed over values[i-window:i].
    """
    z_scores: list[float | None] = []
    for i in range(len(values)):
        if i < window:
            z_scores.append(None)
            continue
        prior = values[i - window : i]
        mean = sum(prior) / window
        variance = sum((v - mean) ** 2 for v in prior) / window
        std = variance**0.5
        if std < _STD_EPSILON:
            z = 0.0 if abs(values[i] - mean) < _STD_EPSILON else float("inf")
        else:
            z = (values[i] - mean) / std
        z_scores.append(z)
    return z_scores


def load_metrics(csv_path: Path) -> list[dict]:
    """Parse metrics.csv into a list of dicts with proper types."""
    rows: list[dict] = []
    with csv_path.open(newline="", encoding="utf-8") as f:
        for raw in csv.DictReader(f):
            rows.append(
                {
                    "timestamp": datetime.fromisoformat(raw["timestamp"]),
                    "service": raw["service"],
                    "latency_ms": float(raw["latency_ms"]),
                    "error_rate": float(raw["error_rate"]),
                    "memory_mb": float(raw["memory_mb"]),
                    "db_connections": float(raw["db_connections"]),
                }
            )
    return rows


def _series_for(rows: list[dict], service: str, metric_name: str) -> tuple[list[datetime], list[float]]:
    filtered = sorted((r for r in rows if r["service"] == service), key=lambda r: r["timestamp"])
    timestamps = [r["timestamp"] for r in filtered]
    values = [r[metric_name] for r in filtered]
    return timestamps, values


def detect_metric_anomaly(
    rows: list[dict],
    service: str,
    metric_name: str,
    window: int = DEFAULT_WINDOW,
    threshold: float = DEFAULT_THRESHOLD,
    min_consecutive: int = 3,
) -> EvidenceItem | None:
    """Return evidence for the start of the first SUSTAINED anomaly, or None.

    A single point crossing |z| > threshold is not enough to flag: with ~2000
    noisy points across a run, random chance alone produces a few 3-sigma
    blips (that's expected under a normal distribution, not a bug). Requiring
    ``min_consecutive`` points in a row crossing the threshold filters out
    those one-off blips while still catching a real, sustained incident —
    which by nature keeps climbing for many points in a row, not just one.
    """
    timestamps, values = _series_for(rows, service, metric_name)
    if len(values) <= window:
        return None
    z_scores = rolling_zscore(values, window)

    streak = 0
    streak_start: int | None = None
    for i, z in enumerate(z_scores):
        if z is not None and abs(z) > threshold:
            if streak == 0:
                streak_start = i
            streak += 1
            if streak >= min_consecutive:
                assert streak_start is not None
                start_z = z_scores[streak_start]
                return EvidenceItem(
                    evidence_id=f"metric:{service}.{metric_name}",
                    source="metrics",
                    service=service,
                    timestamp=timestamps[streak_start].isoformat(),
                    summary=(
                        f"{service} {metric_name} anomaly starting at "
                        f"{timestamps[streak_start].isoformat()}: "
                        f"value={values[streak_start]:.3g}, z-score={start_z:.2f} "
                        f"(window={window}, threshold={threshold}, sustained for "
                        f"{min_consecutive}+ points)"
                    ),
                    data={
                        "value": values[streak_start],
                        "z_score": start_z,
                        "window": window,
                        "threshold": threshold,
                        "min_consecutive": min_consecutive,
                    },
                )
        else:
            streak = 0
            streak_start = None
    return None


def find_anomalies(
    csv_path: Path,
    services: list[str] | None = None,
    metric_names: list[str] | None = None,
    window: int = DEFAULT_WINDOW,
    threshold: float = DEFAULT_THRESHOLD,
    min_consecutive: int = 3,
) -> list[EvidenceItem]:
    """Scan every (service, metric) combination and return evidence for each anomaly found."""
    rows = load_metrics(csv_path)
    services = services or sorted({r["service"] for r in rows})
    metric_names = metric_names or DEFAULT_METRIC_NAMES

    evidence: list[EvidenceItem] = []
    for service in services:
        for metric_name in metric_names:
            item = detect_metric_anomaly(rows, service, metric_name, window, threshold, min_consecutive)
            if item is not None:
                evidence.append(item)
    return evidence
