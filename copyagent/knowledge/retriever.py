"""Lightweight retriever using sklearn TfidfVectorizer (no external DB)."""
import json
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from config import CHUNKS_JSON, TOP_K_RETRIEVAL


def _load_chunks() -> list[dict]:
    if not CHUNKS_JSON.exists():
        return []
    return json.loads(CHUNKS_JSON.read_text(encoding="utf-8"))


def _save_chunks(chunks: list[dict]):
    CHUNKS_JSON.write_text(json.dumps(chunks, ensure_ascii=False, indent=2), encoding="utf-8")


def _build_vectorizer(chunks: list[dict]) -> TfidfVectorizer:
    docs = [c["content"] for c in chunks]
    vec = TfidfVectorizer(max_features=5000, ngram_range=(1, 2))
    vec.fit(docs)
    return vec


def add_chunks(doc_id: int, chunks: list[str]):
    """Store chunks for a document. Remove old chunks first."""
    all_chunks = _load_chunks()
    all_chunks = [c for c in all_chunks if c.get("doc_id") != doc_id]

    for i, text in enumerate(chunks):
        all_chunks.append({
            "chunk_id": f"doc{doc_id}_chunk{i}",
            "doc_id": doc_id,
            "chunk_index": i,
            "content": text
        })
    _save_chunks(all_chunks)
    return len(chunks)


def remove_doc_chunks(doc_id: int):
    all_chunks = _load_chunks()
    all_chunks = [c for c in all_chunks if c.get("doc_id") != doc_id]
    _save_chunks(all_chunks)


def query_chunks(query: str, top_k: int = TOP_K_RETRIEVAL) -> list[dict]:
    """Retrieve most relevant chunks using TF-IDF cosine similarity."""
    all_chunks = _load_chunks()
    if not all_chunks:
        return []

    docs = [c["content"] for c in all_chunks]
    vec = TfidfVectorizer(max_features=5000, ngram_range=(1, 2))
    doc_matrix = vec.fit_transform(docs)
    query_vec = vec.transform([query])
    sims = cosine_similarity(query_vec, doc_matrix).flatten()

    top_indices = np.argsort(sims)[::-1][:top_k]
    return [
        {
            "chunk_id": all_chunks[i]["chunk_id"],
            "content": all_chunks[i]["content"],
            "score": float(round(sims[i], 4))
        }
        for i in top_indices
        if sims[i] > 0
    ]


def get_collection_stats() -> dict:
    return {"chunk_count": len(_load_chunks())}
