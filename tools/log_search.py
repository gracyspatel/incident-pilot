"""Time-windowed, keyword/level/service log search over logs.jsonl.

See ProjectDetails.md §6.3: the agent needs to go from "pool exhausted
errors on checkout between 1:00 and 1:15" to a list of exact, citable log
lines, each with a stable line_id the validator can later check for
existence.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from tools.evidence import EvidenceItem


def load_logs(jsonl_path: Path) -> list[dict]:
    """Parse logs.jsonl into a list of dicts with timestamp as datetime."""
    rows: list[dict] = []
    with jsonl_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            raw = json.loads(line)
            raw["timestamp"] = datetime.fromisoformat(raw["timestamp"])
            rows.append(raw)
    return rows


def search_logs(
    jsonl_path: Path,
    start: datetime | None = None,
    end: datetime | None = None,
    service: str | None = None,
    level: str | None = None,
    keyword: str | None = None,
) -> list[EvidenceItem]:
    """Search logs by time window, service, level and/or keyword (all optional, AND-combined).

    ``keyword`` matches case-insensitively as a substring of the log message.
    Results are sorted by timestamp.
    """
    rows = load_logs(jsonl_path)
    keyword_lower = keyword.lower() if keyword else None

    matches = [
        row
        for row in rows
        if (start is None or row["timestamp"] >= start)
        and (end is None or row["timestamp"] <= end)
        and (service is None or row["service"] == service)
        and (level is None or row["level"] == level)
        and (keyword_lower is None or keyword_lower in row["message"].lower())
    ]
    matches.sort(key=lambda r: r["timestamp"])

    return [
        EvidenceItem(
            evidence_id=f"log:{row['service']}:{row['line_id']}",
            source="logs",
            service=row["service"],
            timestamp=row["timestamp"].isoformat(),
            summary=f"[{row['level']}] {row['message']}",
            data={"level": row["level"], "message": row["message"], "line_id": row["line_id"]},
        )
        for row in matches
    ]


def summarize_matches(matches: list[EvidenceItem]) -> dict:
    """Count + first/last occurrence, so the agent doesn't have to dump thousands of lines."""
    if not matches:
        return {"count": 0, "first_timestamp": None, "last_timestamp": None}
    timestamps = sorted(m.timestamp for m in matches)
    return {"count": len(matches), "first_timestamp": timestamps[0], "last_timestamp": timestamps[-1]}
