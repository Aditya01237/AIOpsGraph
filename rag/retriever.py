import os
import argparse
from typing import List, Dict, Any


KNOWLEDGE_BASE_DIR = "knowledge_base"


INCIDENT_TO_DOCS = {
    "CrashLoopBackOff": [
        "knowledge_base/kubernetes/crashloopbackoff.md",
        "knowledge_base/kubectl/debugging_commands.md",
    ],
    "ImagePullBackOff": [
        "knowledge_base/kubernetes/imagepullbackoff.md",
        "knowledge_base/kubectl/debugging_commands.md",
    ],
    "OOMKilled": [
        "knowledge_base/kubernetes/oomkilled.md",
        "knowledge_base/linux/memory_oom.md",
        "knowledge_base/kubectl/debugging_commands.md",
    ],
}


def read_file(path: str) -> str:
    """
    Read one markdown file and return its text.
    """
    with open(path, "r") as f:
        return f.read()


def load_all_docs() -> List[Dict[str, str]]:
    """
    Load all markdown files from knowledge_base folder.
    """
    docs = []

    for root, _, files in os.walk(KNOWLEDGE_BASE_DIR):
        for file in files:
            if not file.endswith(".md"):
                continue

            path = os.path.join(root, file)

            docs.append({
                "path": path,
                "content": read_file(path)
            })

    return docs


def keyword_score(query: str, content: str) -> int:
    """
    Simple keyword scoring.

    More matching words means higher score.
    This is not embeddings yet. This is our first simple retriever.
    """
    query_words = query.lower().split()
    content_lower = content.lower()

    score = 0

    for word in query_words:
        if word in content_lower:
            score += 1

    return score


def retrieve_by_incident_type(incident_type: str) -> List[Dict[str, Any]]:
    """
    Retrieve fixed useful docs based on incident type.
    """
    paths = INCIDENT_TO_DOCS.get(incident_type, [])

    results = []

    for path in paths:
        if os.path.exists(path):
            results.append({
                "path": path,
                "content": read_file(path)
            })

    return results


def retrieve_by_query(query: str, top_k: int = 3) -> List[Dict[str, Any]]:
    """
    Search all knowledge base docs using simple keyword matching.
    """
    docs = load_all_docs()

    scored_docs = []

    for doc in docs:
        score = keyword_score(query, doc["content"])

        if score > 0:
            scored_docs.append({
                "path": doc["path"],
                "score": score,
                "content": doc["content"]
            })

    scored_docs.sort(
        key=lambda item: item["score"],
        reverse=True
    )

    return scored_docs[:top_k]


def build_retrieval_context(
    docs: List[Dict[str, Any]],
    max_chars_per_doc: int = 1500
) -> str:
    """
    Convert retrieved docs into one text block.

    Later this text block will go into the final RCA report or LLM prompt.
    """
    context_parts = []

    for doc in docs:
        content = doc.get("content", "")

        context_parts.append(
            f"\n--- Source: {doc.get('path')} ---\n"
            f"{content[:max_chars_per_doc]}"
        )

    return "\n".join(context_parts)


def print_results(docs: List[Dict[str, Any]]) -> None:
    """
    Print retrieved docs in terminal.
    """
    if not docs:
        print("No relevant knowledge found.")
        return

    print("\nRetrieved Knowledge")
    print("===================")

    for index, doc in enumerate(docs, start=1):
        print(f"\n{index}. {doc.get('path')}")

        if "score" in doc:
            print(f"   Score: {doc.get('score')}")

        print("-" * 60)
        print(doc.get("content", "")[:800])


def main():
    parser = argparse.ArgumentParser(
        description="Retrieve Kubernetes troubleshooting knowledge"
    )

    parser.add_argument(
        "--incident-type",
        type=str,
        help="Incident type: CrashLoopBackOff, ImagePullBackOff, OOMKilled"
    )

    parser.add_argument(
        "--query",
        type=str,
        help="Free text query"
    )

    parser.add_argument(
        "--top-k",
        type=int,
        default=3,
        help="Number of docs to retrieve"
    )

    args = parser.parse_args()

    if args.incident_type:
        docs = retrieve_by_incident_type(args.incident_type)
        print_results(docs)
        return

    if args.query:
        docs = retrieve_by_query(args.query, args.top_k)
        print_results(docs)
        return

    print("Use one of these commands:")
    print("python rag/retriever.py --incident-type CrashLoopBackOff")
    print("python rag/retriever.py --incident-type ImagePullBackOff")
    print("python rag/retriever.py --incident-type OOMKilled")
    print("python rag/retriever.py --query 'exit code 137 memory limit'")


if __name__ == "__main__":
    main()