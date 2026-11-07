"""Deploy history lookup — what changed and when.

See ProjectDetails.md §6.4: many real incidents follow a change, so
correlating "what deployed right before the symptom started" is a key
clue the agent needs to be able to ask for directly.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from tools.evidence import EvidenceItem


def load_deploys(json_path: Path) -> list[dict]:
    """Parse deploys.json into a list of dicts with timestamp as datetime."""
    raw = json.loads(json_path.read_text(encoding="utf-8"))
    for row in raw:
        row["timestamp"] = datetime.fromisoformat(row["timestamp"])
    return raw


def _to_evidence(row: dict) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=f"deploy:{row['service']}:{row['version']}",
        source="deploys",
        service=row["service"],
        timestamp=row["timestamp"].isoformat(),
        summary=f"{row['service']} deployed {row['version']} at {row['timestamp'].isoformat()}: {row['change_notes']}",
        data={"version": row["version"], "change_notes": row["change_notes"]},
    )


def list_deploys(
    json_path: Path,
    service: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[EvidenceItem]:
    """List deploys, optionally filtered by service and/or time window. Sorted by timestamp."""
    rows = load_deploys(json_path)
    matches = [
        row
        for row in rows
        if (service is None or row["service"] == service)
        and (start is None or row["timestamp"] >= start)
        and (end is None or row["timestamp"] <= end)
    ]
    matches.sort(key=lambda r: r["timestamp"])
    return [_to_evidence(row) for row in matches]


def most_recent_deploy_before(
    json_path: Path, service: str, timestamp: datetime
) -> EvidenceItem | None:
    """The single most recent deploy to ``service`` at or before ``timestamp``, if any.

    This is the direct "what likely caused this" correlation lookup: given a
    symptom's start time, find the last change made to that service before it.
    """
    matches = list_deploys(json_path, service=service, end=timestamp)
    return matches[-1] if matches else None
