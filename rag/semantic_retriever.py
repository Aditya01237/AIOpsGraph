import os
import json
import pickle
import hashlib
import argparse
from typing import Dict, List, Any, Tuple

import numpy as np

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    print("sentence-transformers is not installed.")
    print("Install it using: python3 -m pip install sentence-transformers numpy")
    raise


CHUNKS_FILE = "data/chunks/knowledge_chunks.json"
EMBEDDING_DIR = "data/embeddings"
EMBEDDING_CACHE_FILE = os.path.join(EMBEDDING_DIR, "knowledge_embeddings.pkl")

RETRIEVAL_OUTPUT_DIR = "data/retrieval"
RETRIEVAL_OUTPUT_FILE = os.path.join(RETRIEVAL_OUTPUT_DIR, "semantic_results.json")

DEFAULT_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


INCIDENT_QUERIES = {
    "CrashLoopBackOff": (
        "Kubernetes CrashLoopBackOff container keeps restarting, "
        "back-off restarting failed container, previous logs, startup failure, "
        "restart count increasing, terminated last state, missing config or secret"
    ),
    "ImagePullBackOff": (
        "Kubernetes ImagePullBackOff ErrImagePull failed to pull image, "
        "wrong image tag, image does not exist, private registry, imagePullSecret, "
        "registry authentication failure"
    ),
    "OOMKilled": (
        "Kubernetes OOMKilled container killed due to memory limit, "
        "exit code 137, out of memory, cgroups memory limit, memory leak, "
        "kubectl top pod, previous logs"
    ),
}


def load_chunks(path: str = CHUNKS_FILE) -> List[Dict[str, Any]]:
    """
    Load chunks created by rag/chunker.py.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Chunks file not found: {path}\n"
            "Run this first: python3 rag/chunker.py"
        )

    with open(path, "r") as f:
        data = json.load(f)

    return data.get("chunks", [])


def chunk_to_search_text(chunk: Dict[str, Any]) -> str:
    """
    Build searchable text from chunk metadata and content.
    """
    parts = [
        chunk.get("document_title", ""),
        chunk.get("section_title", ""),
        " ".join(chunk.get("keywords", [])),
        chunk.get("content", "")
    ]

    return "\n".join(parts)


def compute_chunks_hash(chunks: List[Dict[str, Any]]) -> str:
    """
    Create hash so we know whether chunk file changed.
    """
    hash_input = []

    for chunk in chunks:
        hash_input.append({
            "chunk_id": chunk.get("chunk_id"),
            "content": chunk.get("content"),
            "source_path": chunk.get("source_path"),
            "section_title": chunk.get("section_title")
        })

    raw = json.dumps(hash_input, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def load_model(model_name: str) -> SentenceTransformer:
    """
    Load embedding model.
    """
    print(f"Loading embedding model: {model_name}")
    return SentenceTransformer(model_name)


def build_embeddings(
    model: SentenceTransformer,
    chunks: List[Dict[str, Any]]
) -> np.ndarray:
    """
    Convert chunk text into normalized embeddings.
    """
    texts = [chunk_to_search_text(chunk) for chunk in chunks]

    embeddings = model.encode(
        texts,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=True
    )

    return embeddings


def save_embedding_cache(
    chunks: List[Dict[str, Any]],
    embeddings: np.ndarray,
    model_name: str,
    chunks_hash: str,
    cache_file: str = EMBEDDING_CACHE_FILE
) -> None:
    """
    Save embeddings to disk so next search is faster.
    """
    os.makedirs(os.path.dirname(cache_file), exist_ok=True)

    cache_data = {
        "model_name": model_name,
        "chunks_hash": chunks_hash,
        "chunks": chunks,
        "embeddings": embeddings
    }

    with open(cache_file, "wb") as f:
        pickle.dump(cache_data, f)

    print(f"Saved embedding cache: {cache_file}")


def load_embedding_cache(
    model_name: str,
    chunks_hash: str,
    cache_file: str = EMBEDDING_CACHE_FILE
) -> Tuple[List[Dict[str, Any]], np.ndarray]:
    """
    Load embedding cache if model and chunks are unchanged.
    """
    if not os.path.exists(cache_file):
        return [], np.array([])

    with open(cache_file, "rb") as f:
        cache_data = pickle.load(f)

    if cache_data.get("model_name") != model_name:
        return [], np.array([])

    if cache_data.get("chunks_hash") != chunks_hash:
        return [], np.array([])

    chunks = cache_data.get("chunks", [])
    embeddings = cache_data.get("embeddings")

    if embeddings is None:
        return [], np.array([])

    print(f"Loaded embedding cache: {cache_file}")
    return chunks, embeddings


def get_or_build_embeddings(
    chunks: List[Dict[str, Any]],
    model_name: str,
    rebuild_index: bool
) -> Tuple[SentenceTransformer, List[Dict[str, Any]], np.ndarray]:
    """
    Load cached embeddings or build new embeddings.
    """
    chunks_hash = compute_chunks_hash(chunks)

    model = load_model(model_name)

    if not rebuild_index:
        cached_chunks, cached_embeddings = load_embedding_cache(
            model_name=model_name,
            chunks_hash=chunks_hash
        )

        if cached_chunks and cached_embeddings.size > 0:
            return model, cached_chunks, cached_embeddings

    print("Building embeddings from chunks...")

    embeddings = build_embeddings(model, chunks)

    save_embedding_cache(
        chunks=chunks,
        embeddings=embeddings,
        model_name=model_name,
        chunks_hash=chunks_hash
    )

    return model, chunks, embeddings


def semantic_search(
    query: str,
    model: SentenceTransformer,
    chunks: List[Dict[str, Any]],
    embeddings: np.ndarray,
    top_k: int
) -> List[Dict[str, Any]]:
    """
    Search chunks using cosine similarity.

    Because embeddings are normalized, dot product becomes cosine similarity.
    """
    if not chunks:
        return []

    query_embedding = model.encode(
        [query],
        convert_to_numpy=True,
        normalize_embeddings=True
    )[0]

    scores = np.dot(embeddings, query_embedding)

    ranked_indices = np.argsort(scores)[::-1][:top_k]

    results = []

    for rank, index in enumerate(ranked_indices, start=1):
        chunk = chunks[int(index)]
        score = float(scores[int(index)])

        result = {
            "rank": rank,
            "score": round(score, 4),
            "chunk_id": chunk.get("chunk_id"),
            "source_path": chunk.get("source_path"),
            "source_file": chunk.get("source_file"),
            "document_title": chunk.get("document_title"),
            "section_title": chunk.get("section_title"),
            "keywords": chunk.get("keywords", []),
            "content": chunk.get("content", "")
        }

        results.append(result)

    return results


def retrieve_by_query(
    query: str,
    top_k: int,
    model_name: str,
    rebuild_index: bool
) -> List[Dict[str, Any]]:
    """
    Main retrieval function for free-text query.
    """
    chunks = load_chunks(CHUNKS_FILE)

    model, indexed_chunks, embeddings = get_or_build_embeddings(
        chunks=chunks,
        model_name=model_name,
        rebuild_index=rebuild_index
    )

    return semantic_search(
        query=query,
        model=model,
        chunks=indexed_chunks,
        embeddings=embeddings,
        top_k=top_k
    )


def retrieve_by_incident_type(
    incident_type: str,
    top_k: int,
    model_name: str,
    rebuild_index: bool
) -> List[Dict[str, Any]]:
    """
    Retrieve chunks using a predefined incident query.
    """
    query = INCIDENT_QUERIES.get(incident_type)

    if not query:
        query = f"Kubernetes incident troubleshooting {incident_type}"

    return retrieve_by_query(
        query=query,
        top_k=top_k,
        model_name=model_name,
        rebuild_index=rebuild_index
    )


def build_retrieval_context(
    results: List[Dict[str, Any]],
    max_chars_per_chunk: int = 1000
) -> str:
    """
    Convert retrieved chunks into one context block.

    Later this will be attached to RCA report.
    """
    context_parts = []

    for result in results:
        content = result.get("content", "")

        context_parts.append(
            f"\n--- Source: {result.get('source_path')} "
            f"| Section: {result.get('section_title')} "
            f"| Score: {result.get('score')} ---\n"
            f"{content[:max_chars_per_chunk]}"
        )

    return "\n".join(context_parts)


def save_results(
    results: List[Dict[str, Any]],
    query: str,
    output_file: str = RETRIEVAL_OUTPUT_FILE
) -> None:
    """
    Save retrieval results as JSON.
    """
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    output_data = {
        "query": query,
        "total_results": len(results),
        "results": results
    }

    with open(output_file, "w") as f:
        json.dump(output_data, f, indent=2)

    print(f"\nSaved semantic retrieval results: {output_file}")


def print_results(results: List[Dict[str, Any]], show_content_chars: int) -> None:
    """
    Print retrieval results in terminal.
    """
    if not results:
        print("No relevant chunks found.")
        return

    print("\nSemantic Retrieval Results")
    print("==========================")

    for result in results:
        print()
        print(f"Rank: {result.get('rank')}")
        print(f"Score: {result.get('score')}")
        print(f"Source: {result.get('source_path')}")
        print(f"Document: {result.get('document_title')}")
        print(f"Section: {result.get('section_title')}")
        print(f"Keywords: {result.get('keywords')}")
        print("-" * 70)
        print(result.get("content", "")[:show_content_chars])


def main():
    parser = argparse.ArgumentParser(
        description="Semantic retriever for AIOpsGraph knowledge chunks"
    )

    parser.add_argument(
        "--query",
        type=str,
        help="Free-text query for semantic search"
    )

    parser.add_argument(
        "--incident-type",
        type=str,
        help="Incident type: CrashLoopBackOff, ImagePullBackOff, OOMKilled"
    )

    parser.add_argument(
        "--top-k",
        type=int,
        default=3,
        help="Number of chunks to retrieve"
    )

    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_MODEL_NAME,
        help="SentenceTransformer model name"
    )

    parser.add_argument(
        "--rebuild-index",
        action="store_true",
        help="Force rebuild embedding cache"
    )

    parser.add_argument(
        "--save",
        action="store_true",
        help="Save retrieval results to data/retrieval/semantic_results.json"
    )

    parser.add_argument(
        "--show-content-chars",
        type=int,
        default=700,
        help="Number of content characters to print per result"
    )

    args = parser.parse_args()

    if not args.query and not args.incident_type:
        print("Use one of these:")
        print("python3 rag/semantic_retriever.py --query 'container killed due to memory pressure'")
        print("python3 rag/semantic_retriever.py --incident-type OOMKilled")
        return

    if args.incident_type:
        search_query = INCIDENT_QUERIES.get(
            args.incident_type,
            f"Kubernetes incident troubleshooting {args.incident_type}"
        )

        results = retrieve_by_incident_type(
            incident_type=args.incident_type,
            top_k=args.top_k,
            model_name=args.model,
            rebuild_index=args.rebuild_index
        )
    else:
        search_query = args.query

        results = retrieve_by_query(
            query=args.query,
            top_k=args.top_k,
            model_name=args.model,
            rebuild_index=args.rebuild_index
        )

    print_results(results, args.show_content_chars)

    if args.save:
        save_results(results, search_query)


if __name__ == "__main__":
    main()