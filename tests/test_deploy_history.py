"""Tests for the deploy history lookup tool."""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from simulator.generate import generate_incident
from tools.deploy_history import list_deploys, most_recent_deploy_before


@pytest.fixture(scope="module")
def incident_dir(tmp_path_factory: pytest.TempPathFactory):
    root = tmp_path_factory.mktemp("incidents")
    return generate_incident(seed=42, incident_id="inc_test", output_root=root)


@pytest.fixture(scope="module")
def answer_key(incident_dir) -> dict:
    return json.loads((incident_dir / "answer_key.json").read_text(encoding="utf-8"))


class TestListDeploys:
    def test_lists_all_deploys_unfiltered(self, incident_dir) -> None:
        deploys = list_deploys(incident_dir / "deploys.json")
        assert len(deploys) >= 2  # at least the background ones + the bad one

    def test_service_filter(self, incident_dir, answer_key) -> None:
        service = answer_key["root_cause_service"]
        deploys = list_deploys(incident_dir / "deploys.json", service=service)
        assert len(deploys) >= 1
        assert all(d.service == service for d in deploys)

    def test_includes_the_bad_deploy_matching_answer_key(self, incident_dir, answer_key) -> None:
        service = answer_key["root_cause_service"]
        deploys = list_deploys(incident_dir / "deploys.json", service=service)
        evidence_ids = {d.evidence_id for d in deploys}
        bad_deploy_id = next(e for e in answer_key["key_evidence"] if e.startswith("deploy:"))
        assert bad_deploy_id in evidence_ids

    def test_results_are_sorted_by_timestamp(self, incident_dir) -> None:
        deploys = list_deploys(incident_dir / "deploys.json")
        timestamps = [d.timestamp for d in deploys]
        assert timestamps == sorted(timestamps)


class TestMostRecentDeployBefore:
    def test_finds_the_bad_deploy_right_before_fault_start(self, incident_dir, answer_key) -> None:
        service = answer_key["root_cause_service"]
        fault_start = datetime.fromisoformat(answer_key["fault_start"])
        deploy = most_recent_deploy_before(incident_dir / "deploys.json", service, fault_start)
        assert deploy is not None
        assert deploy.timestamp == answer_key["deploy_time"]

    def test_returns_none_when_no_deploy_precedes_timestamp(self, incident_dir, answer_key) -> None:
        service = answer_key["root_cause_service"]
        far_past = datetime.fromisoformat("2000-01-01T00:00:00+00:00")
        deploy = most_recent_deploy_before(incident_dir / "deploys.json", service, far_past)
        assert deploy is None
