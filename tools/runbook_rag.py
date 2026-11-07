"""Runbook retrieval: chunk markdown runbooks, embed locally, store in ChromaDB.

See ProjectDetails.md §6.5. The chunking and the decision of what to embed
(title + section heading + body, so short sections still carry context) is
ours; the embedding model (Sentence Transformers) and the vector store
(ChromaDB) are library-provided — see ProjectDetails.md §11.

Runbooks are chunked by "## " section headings (Symptoms, Likely causes,
Diagnosis steps, Fix, Prevention, ...), since that's the granularity a
human on-call engineer actually wants back: "the diagnosis steps for pool
exhaustion," not the whole runbook or one sentence.
"""

from __future__ import annotations

from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

from tools.evidence import EvidenceItem

# [Suggestion] A small, fast, local model — good enough for short runbook
# sections and cheap to run on CPU. Not an LLM model name (those go in the
# agent's own config in Phase 3), so a module constant is fine here.
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"

DEFAULT_RUNBOOKS_DIR = Path(__file__).resolve().parent.parent / "data" / "runbooks"
DEFAULT_PERSIST_DIR = Path(__file__).resolve().parent.parent / "chroma_db"
DEFAULT_COLLECTION_NAME = "runbooks"

_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    """Lazy singleton: loading the model takes a moment, so do it once."""
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _model


def embed_texts(texts: list[str]) -> list[list[float]]:
    model = _get_model()
    return model.encode(list(texts)).tolist()


def chunk_runbook(path: Path) -> list[dict]:
    """Split one runbook into (title, heading, text) chunks by '## ' headings."""
    lines = path.read_text(encoding="utf-8").splitlines()
    title: str | None = None
    chunks: list[dict] = []
    heading: str | None = None
    body: list[str] = []

    def flush() -> None:
        if heading is not None:
            chunks.append({"source_file": path.stem, "title": title, "heading": heading, "text": "\n".join(body).strip()})

    for line in lines:
        if line.startswith("# ") and title is None:
            title = line[2:].strip()
            continue
        if line.startswith("## "):
            flush()
            heading = line[3:].strip()
            body = []
            continue
        body.append(line)
    flush()
    return chunks


def chunk_runbooks_dir(runbooks_dir: Path = DEFAULT_RUNBOOKS_DIR) -> list[dict]:
    chunks: list[dict] = []
    for md_file in sorted(runbooks_dir.glob("*.md")):
        chunks.extend(chunk_runbook(md_file))
    return chunks


def build_index(
    runbooks_dir: Path = DEFAULT_RUNBOOKS_DIR,
    persist_dir: Path = DEFAULT_PERSIST_DIR,
    collection_name: str = DEFAULT_COLLECTION_NAME,
) -> int:
    """(Re)build the ChromaDB collection from the runbooks on disk. Returns chunk count."""
    chunks = chunk_runbooks_dir(runbooks_dir)
    documents = [f"{c['title']} - {c['heading']}\n{c['text']}" for c in chunks]
    ids = [f"{c['source_file']}::{c['heading']}" for c in chunks]
    embeddings = embed_texts(documents)

    client = chromadb.PersistentClient(path=str(persist_dir))
    try:
        client.delete_collection(collection_name)
    except Exception:
        pass  # collection didn't exist yet — fine
    collection = client.create_collection(collection_name)
    collection.add(
        ids=ids,
        embeddings=embeddings,
        documents=documents,
        metadatas=[
            {"source_file": c["source_file"], "title": c["title"] or "", "heading": c["heading"]} for c in chunks
        ],
    )
    return len(chunks)


def query_runbooks(
    query: str,
    persist_dir: Path = DEFAULT_PERSIST_DIR,
    top_k: int = 3,
    collection_name: str = DEFAULT_COLLECTION_NAME,
) -> list[EvidenceItem]:
    """Return the top_k most relevant runbook sections for ``query``.

    ``data["distance"]`` is a vector distance (lower = more similar), not a
    0-1 confidence score — don't present it to the user as a percentage.
    """
    client = chromadb.PersistentClient(path=str(persist_dir))
    collection = client.get_collection(collection_name)
    query_embedding = embed_texts([query])[0]
    results = collection.query(query_embeddings=[query_embedding], n_results=top_k)

    evidence: list[EvidenceItem] = []
    for doc, meta, distance in zip(results["documents"][0], results["metadatas"][0], results["distances"][0]):
        evidence.append(
            EvidenceItem(
                evidence_id=f"runbook:{meta['source_file']}:{meta['heading']}",
                source="runbook",
                service=None,
                timestamp=None,
                summary=f"{meta['title']} — {meta['heading']} (distance={distance:.3f})",
                data={
                    "text": doc,
                    "distance": distance,
                    "source_file": meta["source_file"],
                    "heading": meta["heading"],
                },
            )
        )
    return evidence


def main() -> None:
    count = build_index()
    print(f"Indexed {count} runbook sections from {DEFAULT_RUNBOOKS_DIR} -> {DEFAULT_PERSIST_DIR}")


if __name__ == "__main__":
    main()
