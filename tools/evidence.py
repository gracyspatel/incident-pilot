"""Shared evidence format returned by every investigation tool.

Every tool (metrics, log search, deploy history, runbook RAG) returns a
list of ``EvidenceItem``. Using one shape across all four tools means the
Analyst agent (Phase 3) can cite any of them uniformly, and the Validator
(Phase 3) can check "does this cited evidence_id actually exist" with one
code path instead of one per tool.

``evidence_id`` deliberately uses the same ``<kind>:<service>:<detail>``
format as the simulator's answer_key.json (see simulator/generate.py
_build_answer_key). That is not a coincidence: it means the evaluation
harness (Phase 5) can compare "evidence IDs the agent cited" directly
against "key_evidence IDs in the answer key" with zero translation layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

EvidenceSource = Literal["metrics", "logs", "deploys", "runbook"]


@dataclass
class EvidenceItem:
    """One piece of evidence a tool found, citable by its evidence_id."""

    evidence_id: str
    source: EvidenceSource
    service: str | None
    timestamp: str | None  # ISO 8601, when applicable
    summary: str  # one-line, human-readable
    data: dict[str, Any] = field(default_factory=dict)  # raw fields for detail/debugging

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "source": self.source,
            "service": self.service,
            "timestamp": self.timestamp,
            "summary": self.summary,
            "data": self.data,
        }
