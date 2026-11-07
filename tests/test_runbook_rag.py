"""Tests for runbook chunking and retrieval.

Retrieval tests hit a real (small, local) embedding model, so they're
naturally slower than the other tool tests — the model is loaded once per
test session via module-scoped fixtures.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.runbook_rag import DEFAULT_RUNBOOKS_DIR, build_index, chunk_runbook, chunk_runbooks_dir, query_runbooks

POOL_RUNBOOK = DEFAULT_RUNBOOKS_DIR / "connection-pool-exhausted.md"


class TestChunking:
    def test_chunks_connection_pool_runbook_by_section(self) -> None:
        chunks = chunk_runbook(POOL_RUNBOOK)
        headings = [c["heading"] for c in chunks]
        assert headings == ["Symptoms", "Likely causes", "Diagnosis steps", "Fix", "Prevention"]

    def test_title_is_extracted_from_top_level_heading(self) -> None:
        chunks = chunk_runbook(POOL_RUNBOOK)
        assert all(c["title"] == "Runbook: Database Connection Pool Exhausted" for c in chunks)

    def test_each_chunk_has_non_empty_text(self) -> None:
        chunks = chunk_runbook(POOL_RUNBOOK)
        assert all(c["text"].strip() for c in chunks)

    def test_chunk_runbooks_dir_covers_all_three_runbooks(self) -> None:
        chunks = chunk_runbooks_dir(DEFAULT_RUNBOOKS_DIR)
        source_files = {c["source_file"] for c in chunks}
        assert source_files == {"connection-pool-exhausted", "memory-leak", "dependency-outage"}


@pytest.fixture(scope="module")
def built_index(tmp_path_factory: pytest.TempPathFactory) -> Path:
    persist_dir = tmp_path_factory.mktemp("chroma_test")
    build_index(runbooks_dir=DEFAULT_RUNBOOKS_DIR, persist_dir=persist_dir)
    return persist_dir


class TestRetrieval:
    def test_pool_exhausted_symptom_retrieves_the_pool_exhausted_runbook(self, built_index: Path) -> None:
        results = query_runbooks(
            "checkout service throwing pool exhausted errors and latency spike after a deploy",
            persist_dir=built_index,
            top_k=1,
        )
        assert len(results) == 1
        assert results[0].data["source_file"] == "connection-pool-exhausted"

    def test_memory_symptom_retrieves_the_memory_leak_runbook(self, built_index: Path) -> None:
        results = query_runbooks(
            "service memory climbing steadily then OutOfMemoryError and repeated restarts",
            persist_dir=built_index,
            top_k=1,
        )
        assert len(results) == 1
        assert results[0].data["source_file"] == "memory-leak"

    def test_dependency_symptom_retrieves_the_dependency_outage_runbook(self, built_index: Path) -> None:
        results = query_runbooks(
            "timeouts calling payment-api downstream dependency, latency clustered at timeout value",
            persist_dir=built_index,
            top_k=1,
        )
        assert len(results) == 1
        assert results[0].data["source_file"] == "dependency-outage"

    def test_evidence_item_shape(self, built_index: Path) -> None:
        results = query_runbooks("pool exhausted", persist_dir=built_index, top_k=3)
        assert len(results) == 3
        for item in results:
            assert item.evidence_id.startswith("runbook:")
            assert item.source == "runbook"
            assert "text" in item.data
            assert isinstance(item.data["distance"], float)

    def test_top_k_is_respected(self, built_index: Path) -> None:
        results = query_runbooks("pool exhausted", persist_dir=built_index, top_k=2)
        assert len(results) == 2
