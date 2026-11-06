"""Tests for the Phase 1 incident simulator.

Verifies the three things the task description asks for:
1. All expected output files exist.
2. The fault appears AFTER the deploy that caused it.
3. The answer key matches what was actually injected into the data.

Tests write into a temporary directory (not data/incidents/) so running the
suite never depends on, or mutates, a previously generated incident.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from simulator.generate import generate_incident

SEED = 42
INCIDENT_ID = "inc_test"


@pytest.fixture(scope="module")
def incident_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("incidents")
    return generate_incident(seed=SEED, incident_id=INCIDENT_ID, output_root=root)


@pytest.fixture(scope="module")
def answer_key(incident_dir: Path) -> dict:
    return json.loads((incident_dir / "answer_key.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def log_lines(incident_dir: Path) -> list[dict]:
    text = (incident_dir / "logs.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line]


@pytest.fixture(scope="module")
def deploy_records(incident_dir: Path) -> list[dict]:
    return json.loads((incident_dir / "deploys.json").read_text(encoding="utf-8"))


class TestOutputFilesExist:
    def test_all_expected_files_are_written(self, incident_dir: Path) -> None:
        for filename in ("logs.jsonl", "metrics.csv", "deploys.json", "answer_key.json"):
            path = incident_dir / filename
            assert path.exists(), f"missing expected output file: {filename}"
            assert path.stat().st_size > 0, f"{filename} is empty"

    def test_logs_are_non_empty_and_have_unique_ids(self, log_lines: list[dict]) -> None:
        assert len(log_lines) > 0
        ids = [line["line_id"] for line in log_lines]
        assert len(ids) == len(set(ids)), "log line IDs must be unique"

    def test_metrics_csv_has_header_and_rows(self, incident_dir: Path) -> None:
        lines = (incident_dir / "metrics.csv").read_text(encoding="utf-8").splitlines()
        assert lines[0] == "timestamp,service,latency_ms,error_rate,memory_mb,db_connections"
        assert len(lines) > 1


class TestFaultTiming:
    def test_fault_start_is_after_deploy_time(self, answer_key: dict) -> None:
        deploy_time = datetime.fromisoformat(answer_key["deploy_time"])
        fault_start = datetime.fromisoformat(answer_key["fault_start"])
        assert fault_start > deploy_time

    def test_bad_deploy_is_in_deploy_history_before_fault_start(
        self, answer_key: dict, deploy_records: list[dict]
    ) -> None:
        service = answer_key["root_cause_service"]
        fault_start = datetime.fromisoformat(answer_key["fault_start"])
        matching = [d for d in deploy_records if d["service"] == service]
        assert matching, f"no deploy found for root-cause service {service!r}"
        bad_deploy = matching[-1]  # the injected fault deploy is the service's last deploy
        bad_deploy_time = datetime.fromisoformat(bad_deploy["timestamp"])
        assert bad_deploy_time < fault_start

    def test_no_pool_exhausted_errors_before_fault_start(
        self, answer_key: dict, log_lines: list[dict]
    ) -> None:
        fault_start = datetime.fromisoformat(answer_key["fault_start"])
        for line in log_lines:
            if "pool exhausted" in line["message"]:
                ts = datetime.fromisoformat(line["timestamp"])
                assert ts >= fault_start, (
                    f"pool-exhausted error {line['line_id']} at {ts} occurs before "
                    f"fault_start {fault_start}"
                )

    def test_pool_exhausted_errors_exist_after_fault_start(self, log_lines: list[dict]) -> None:
        assert any("pool exhausted" in line["message"] for line in log_lines)


class TestAnswerKeyMatchesInjectedFault:
    def test_fault_type_and_service(self, answer_key: dict) -> None:
        assert answer_key["fault_type"] == "bad_deploy_pool_exhaustion"
        assert answer_key["root_cause_service"] == "checkout"
        assert answer_key["new_pool_size"] < answer_key["old_pool_size"]

    def test_key_evidence_log_ids_exist_and_are_pool_exhausted_errors(
        self, answer_key: dict, log_lines: list[dict]
    ) -> None:
        logs_by_id = {line["line_id"]: line for line in log_lines}
        log_evidence_ids = [
            e.split(":")[-1] for e in answer_key["key_evidence"] if e.startswith("log:")
        ]
        assert log_evidence_ids, "answer key should cite at least one log line"
        for line_id in log_evidence_ids:
            assert line_id in logs_by_id, f"cited line_id {line_id} does not exist in logs.jsonl"
            cited_line = logs_by_id[line_id]
            assert cited_line["level"] == "ERROR"
            assert "pool exhausted" in cited_line["message"]

    def test_key_evidence_includes_the_bad_deploy(self, answer_key: dict) -> None:
        service = answer_key["root_cause_service"]
        version = answer_key["root_cause_change"].split()[-1]
        assert f"deploy:{service}:{version}" in answer_key["key_evidence"]

    def test_root_cause_change_mentions_pool_in_deploy_history(
        self, answer_key: dict, deploy_records: list[dict]
    ) -> None:
        version = answer_key["root_cause_change"].split()[-1]
        matching = [d for d in deploy_records if d["version"] == version]
        assert len(matching) == 1
        assert "pool" in matching[0]["change_notes"].lower()


class TestReproducibility:
    def test_same_seed_produces_identical_answer_key(self, tmp_path: Path) -> None:
        dir_a = generate_incident(seed=SEED, incident_id="a", output_root=tmp_path / "run_a")
        dir_b = generate_incident(seed=SEED, incident_id="a", output_root=tmp_path / "run_b")
        key_a = (dir_a / "answer_key.json").read_text(encoding="utf-8")
        key_b = (dir_b / "answer_key.json").read_text(encoding="utf-8")
        assert key_a == key_b

    def test_same_seed_produces_identical_log_count(self, tmp_path: Path) -> None:
        dir_a = generate_incident(seed=SEED, incident_id="a", output_root=tmp_path / "run_a")
        dir_b = generate_incident(seed=SEED, incident_id="a", output_root=tmp_path / "run_b")
        lines_a = (dir_a / "logs.jsonl").read_text(encoding="utf-8").splitlines()
        lines_b = (dir_b / "logs.jsonl").read_text(encoding="utf-8").splitlines()
        assert lines_a == lines_b
