import os
import sys
import json
import argparse
from typing import Dict, List, Any


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)


from rca_engine.rca_rules import load_graph, analyze_all_incidents
from rag.semantic_retriever import (
    load_chunks,
    get_or_build_embeddings,
    semantic_search,
    build_retrieval_context,
    INCIDENT_QUERIES,
    DEFAULT_MODEL_NAME,
)


OUTPUT_DIR = "data/rca"
FINAL_REPORT_FILE = os.path.join(OUTPUT_DIR, "final_rca_report.json")


def build_incident_search_query(rca_report: Dict[str, Any]) -> str:
    """
    Build semantic search query using incident type, root cause, evidence, and fixes.
    """

    incident_type = rca_report.get("incident_type", "Unknown")
    top_root_cause = rca_report.get("top_root_cause") or {}

    query_parts = []

    predefined_query = INCIDENT_QUERIES.get(incident_type)

    if predefined_query:
        query_parts.append(predefined_query)
    else:
        query_parts.append(f"Kubernetes troubleshooting for {incident_type}")

    root_cause = top_root_cause.get("root_cause")
    category = top_root_cause.get("category")

    if root_cause:
        query_parts.append(str(root_cause))

    if category:
        query_parts.append(str(category))

    evidence_items = top_root_cause.get("evidence", [])

    for evidence in evidence_items[:5]:
        query_parts.append(str(evidence))

    recommended_fixes = top_root_cause.get("recommended_fix", [])

    for fix in recommended_fixes[:3]:
        query_parts.append(str(fix))

    return " ".join(query_parts)


def extract_retrieved_sources(results: List[Dict[str, Any]]) -> List[str]:
    """
    Extract unique source paths from semantic retrieval results.
    """

    sources = []

    for result in results:
        source_path = result.get("source_path")

        if source_path and source_path not in sources:
            sources.append(source_path)

    return sources


def build_final_report(
    rca_report: Dict[str, Any],
    semantic_results: List[Dict[str, Any]],
    retrieval_query: str
) -> Dict[str, Any]:
    """
    Add semantic retrieval output to one RCA report.
    """

    retrieved_sources = extract_retrieved_sources(semantic_results)

    retrieval_context = build_retrieval_context(
        results=semantic_results,
        max_chars_per_chunk=1000
    )

    final_report = {
        "incident_id": rca_report.get("incident_id"),
        "incident_type": rca_report.get("incident_type"),
        "timestamp": rca_report.get("timestamp"),
        "top_root_cause": rca_report.get("top_root_cause"),
        "all_candidates": rca_report.get("candidates", []),
        "retrieval_type": "semantic",
        "retrieval_query": retrieval_query,
        "retrieved_sources": retrieved_sources,
        "retrieved_chunks": semantic_results,
        "retrieved_knowledge": retrieval_context
    }

    return final_report


def build_all_final_reports(
    rca_reports: List[Dict[str, Any]],
    top_k: int,
    model_name: str,
    rebuild_index: bool
) -> List[Dict[str, Any]]:
    """
    Build final RCA reports using semantic retrieval.

    Important:
    The embedding model and chunk embeddings are loaded only once.
    This avoids reloading model again and again for every incident.
    """

    chunks = load_chunks()

    model, indexed_chunks, embeddings = get_or_build_embeddings(
        chunks=chunks,
        model_name=model_name,
        rebuild_index=rebuild_index
    )

    final_reports = []

    for rca_report in rca_reports:
        retrieval_query = build_incident_search_query(rca_report)

        semantic_results = semantic_search(
            query=retrieval_query,
            model=model,
            chunks=indexed_chunks,
            embeddings=embeddings,
            top_k=top_k
        )

        final_report = build_final_report(
            rca_report=rca_report,
            semantic_results=semantic_results,
            retrieval_query=retrieval_query
        )

        final_reports.append(final_report)

    return final_reports


def save_final_reports(final_reports: List[Dict[str, Any]]) -> None:
    """
    Save final RCA reports.
    """

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with open(FINAL_REPORT_FILE, "w") as f:
        json.dump(final_reports, f, indent=2)

    print(f"\nSaved final RCA report: {FINAL_REPORT_FILE}")


def print_final_report(report: Dict[str, Any]) -> None:
    """
    Print final RCA report in terminal.
    """

    print("\nFinal RCA Report")
    print("================")
    print(f"Incident ID: {report.get('incident_id')}")
    print(f"Incident Type: {report.get('incident_type')}")
    print(f"Timestamp: {report.get('timestamp')}")
    print(f"Retrieval Type: {report.get('retrieval_type')}")

    top = report.get("top_root_cause")

    if top:
        print("\nTop Root Cause")
        print("--------------")
        print(f"Cause: {top.get('root_cause')}")
        print(f"Category: {top.get('category')}")
        print(f"Confidence: {top.get('confidence')}")

        print("\nRecommended Fixes")
        print("-----------------")
        for fix in top.get("recommended_fix", []):
            print(f"- {fix}")

        print("\nEvidence")
        print("--------")
        for item in top.get("evidence", [])[:5]:
            print(f"- {item}")

    else:
        print("\nNo root cause candidate found.")

    print("\nSemantic Retrieval Query")
    print("------------------------")
    query = report.get("retrieval_query", "")
    print(query[:500])

    print("\nRetrieved Sources")
    print("-----------------")

    sources = report.get("retrieved_sources", [])

    if not sources:
        print("No knowledge base sources retrieved.")
    else:
        for source in sources:
            print(f"- {source}")

    print("\nTop Retrieved Chunks")
    print("--------------------")

    chunks = report.get("retrieved_chunks", [])

    if not chunks:
        print("No semantic chunks retrieved.")
    else:
        for chunk in chunks[:3]:
            print(
                f"- Rank {chunk.get('rank')} | "
                f"Score {chunk.get('score')} | "
                f"{chunk.get('source_path')} | "
                f"Section: {chunk.get('section_title')}"
            )

    print("\nRetrieved Knowledge Preview")
    print("---------------------------")

    knowledge = report.get("retrieved_knowledge", "")

    if knowledge:
        print(knowledge[:1200])
    else:
        print("No retrieved knowledge available.")


def main():
    parser = argparse.ArgumentParser(
        description="Run final AIOpsGraph RCA pipeline with semantic retrieval"
    )

    parser.add_argument(
        "--save",
        action="store_true",
        help="Save final RCA report to data/rca/final_rca_report.json"
    )

    parser.add_argument(
        "--top-k",
        type=int,
        default=3,
        help="Number of semantic chunks to retrieve per incident"
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
        help="Force rebuild semantic embedding index"
    )

    args = parser.parse_args()

    graph = load_graph()

    rca_reports = analyze_all_incidents(graph)

    if not rca_reports:
        print("No incidents found in graph.")
        return

    final_reports = build_all_final_reports(
        rca_reports=rca_reports,
        top_k=args.top_k,
        model_name=args.model,
        rebuild_index=args.rebuild_index
    )

    for report in final_reports:
        print_final_report(report)

    if args.save:
        save_final_reports(final_reports)


if __name__ == "__main__":
    main()