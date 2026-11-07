"""Tests for the rolling z-score anomaly detector."""

from __future__ import annotations

from datetime import datetime

import pytest

from simulator.generate import generate_incident
from tools.metrics_tool import detect_metric_anomaly, find_anomalies, load_metrics, rolling_zscore


class TestRollingZscorePureFunction:
    def test_flat_series_has_zero_zscore(self) -> None:
        values = [10.0] * 20
        z_scores = rolling_zscore(values, window=5)
        assert all(z is None for z in z_scores[:5])
        assert all(z == 0.0 for z in z_scores[5:])

    def test_spike_is_flagged(self) -> None:
        values = [10.0] * 10 + [1000.0]
        z_scores = rolling_zscore(values, window=10)
        assert z_scores[-1] is not None
        assert z_scores[-1] > 3.0

    def test_not_enough_history_returns_none(self) -> None:
        values = [1.0, 2.0, 3.0]
        z_scores = rolling_zscore(values, window=10)
        assert all(z is None for z in z_scores)

    def test_gradual_drift_within_window_is_not_flagged(self) -> None:
        # Slowly increasing values: each new point is close to its own
        # recent history, so z-scores should stay small.
        values = [float(i) for i in range(30)]
        z_scores = rolling_zscore(values, window=10)
        for z in z_scores[10:]:
            assert z is not None
            assert abs(z) < 3.0


@pytest.fixture(scope="module")
def incident_dir(tmp_path_factory: pytest.TempPathFactory):
    root = tmp_path_factory.mktemp("incidents")
    return generate_incident(seed=42, incident_id="inc_test", output_root=root)


class TestFindAnomaliesOnSimulatedIncident:
    def test_checkout_latency_and_error_rate_are_flagged(self, incident_dir) -> None:
        evidence = find_anomalies(incident_dir / "metrics.csv")
        evidence_ids = {e.evidence_id for e in evidence}
        assert "metric:checkout.latency_ms" in evidence_ids
        assert "metric:checkout.error_rate" in evidence_ids

    def test_db_connections_step_change_is_a_known_blind_spot(self, incident_dir) -> None:
        """Documents a real limitation found while building this, not a bug.

        db_connections doesn't ramp like latency/error_rate — it steps
        instantly to a new, almost-noise-free constant (the new pool size)
        and stays there. A rolling window detector only ever sees ONE point
        where the window is still "normal" immediately before the new
        constant value fills it — after that the window re-baselines around
        the new value and z collapses back near 0. requiring a streak of
        min_consecutive points (needed to kill false positives elsewhere,
        see TestRollingZscorePureFunction) means this single-point blip never
        qualifies. This is exactly why the agent uses log search and deploy
        history too, not just metrics — log search catches the pool-exhausted
        errors instantly regardless of this blind spot.
        """
        evidence = find_anomalies(incident_dir / "metrics.csv")
        evidence_ids = {e.evidence_id for e in evidence}
        assert "metric:checkout.db_connections" not in evidence_ids

    def test_unaffected_services_have_no_anomalies(self, incident_dir) -> None:
        evidence = find_anomalies(incident_dir / "metrics.csv")
        flagged_services = {e.service for e in evidence}
        for unaffected in ("web", "cache"):
            assert unaffected not in flagged_services

    def test_checkout_memory_is_not_flagged(self, incident_dir) -> None:
        # The fault never touches memory, so this must stay clean.
        evidence = find_anomalies(incident_dir / "metrics.csv")
        evidence_ids = {e.evidence_id for e in evidence}
        assert "metric:checkout.memory_mb" not in evidence_ids

    def test_anomaly_timestamp_is_at_or_after_fault_start(self, incident_dir) -> None:
        import json

        answer_key = json.loads((incident_dir / "answer_key.json").read_text(encoding="utf-8"))
        fault_start = datetime.fromisoformat(answer_key["fault_start"])

        rows = load_metrics(incident_dir / "metrics.csv")
        item = detect_metric_anomaly(rows, "checkout", "latency_ms")
        assert item is not None
        anomaly_time = datetime.fromisoformat(item.timestamp)
        assert anomaly_time >= fault_start

    def test_evidence_item_shape(self, incident_dir) -> None:
        evidence = find_anomalies(incident_dir / "metrics.csv")
        item = next(e for e in evidence if e.evidence_id == "metric:checkout.latency_ms")
        assert item.source == "metrics"
        assert item.service == "checkout"
        assert "z_score" in item.data
        assert abs(item.data["z_score"]) > 3.0
