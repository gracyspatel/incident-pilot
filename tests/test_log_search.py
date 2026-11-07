"""Tests for the time/service/level/keyword log search tool."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from simulator.generate import generate_incident
from tools.log_search import search_logs, summarize_matches


@pytest.fixture(scope="module")
def incident_dir(tmp_path_factory: pytest.TempPathFactory):
    root = tmp_path_factory.mktemp("incidents")
    return generate_incident(seed=42, incident_id="inc_test", output_root=root)


@pytest.fixture(scope="module")
def answer_key(incident_dir) -> dict:
    return json.loads((incident_dir / "answer_key.json").read_text(encoding="utf-8"))


class TestKeywordAndServiceSearch:
    def test_pool_exhausted_keyword_finds_only_checkout_errors(self, incident_dir, answer_key) -> None:
        matches = search_logs(incident_dir / "logs.jsonl", keyword="pool exhausted")
        assert len(matches) > 0
        for m in matches:
            assert m.service == answer_key["root_cause_service"]
            assert m.data["level"] == "ERROR"

    def test_keyword_search_is_case_insensitive(self, incident_dir) -> None:
        lower = search_logs(incident_dir / "logs.jsonl", keyword="pool exhausted")
        upper = search_logs(incident_dir / "logs.jsonl", keyword="POOL EXHAUSTED")
        assert {m.evidence_id for m in lower} == {m.evidence_id for m in upper}

    def test_service_filter_excludes_other_services(self, incident_dir) -> None:
        matches = search_logs(incident_dir / "logs.jsonl", service="web")
        assert len(matches) > 0
        assert all(m.service == "web" for m in matches)

    def test_level_filter(self, incident_dir) -> None:
        errors = search_logs(incident_dir / "logs.jsonl", level="ERROR")
        assert len(errors) > 0
        assert all(m.data["level"] == "ERROR" for m in errors)


class TestTimeWindowSearch:
    def test_window_before_fault_has_no_pool_exhausted_errors(self, incident_dir, answer_key) -> None:
        fault_start = datetime.fromisoformat(answer_key["fault_start"])
        matches = search_logs(
            incident_dir / "logs.jsonl",
            end=fault_start - timedelta(seconds=1),
            keyword="pool exhausted",
        )
        assert matches == []

    def test_window_after_fault_has_pool_exhausted_errors(self, incident_dir, answer_key) -> None:
        fault_start = datetime.fromisoformat(answer_key["fault_start"])
        matches = search_logs(
            incident_dir / "logs.jsonl", start=fault_start, keyword="pool exhausted"
        )
        assert len(matches) > 0

    def test_results_are_sorted_by_timestamp(self, incident_dir) -> None:
        matches = search_logs(incident_dir / "logs.jsonl", service="checkout")
        timestamps = [m.timestamp for m in matches]
        assert timestamps == sorted(timestamps)


class TestEvidenceShapeAndSummary:
    def test_evidence_id_matches_answer_key_format(self, incident_dir, answer_key) -> None:
        matches = search_logs(incident_dir / "logs.jsonl", keyword="pool exhausted")
        evidence_ids = {m.evidence_id for m in matches}
        log_evidence_ids = {e for e in answer_key["key_evidence"] if e.startswith("log:")}
        assert log_evidence_ids.issubset(evidence_ids)

    def test_summarize_matches(self, incident_dir) -> None:
        matches = search_logs(incident_dir / "logs.jsonl", keyword="pool exhausted")
        summary = summarize_matches(matches)
        assert summary["count"] == len(matches)
        assert summary["first_timestamp"] <= summary["last_timestamp"]

    def test_summarize_empty_matches(self) -> None:
        assert summarize_matches([]) == {"count": 0, "first_timestamp": None, "last_timestamp": None}
