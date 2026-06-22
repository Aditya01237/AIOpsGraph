import os
import sys
import json
import argparse
from typing import Dict, List, Any


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)


from rca_engine.rca_rules import load_graph, analyze_all_incidents
from rag.retriever import retrieve_by_incident_type, build_retrieval_context


OUTPUT_DIR = "data/rca"
FINAL_REPORT_FILE = os.path.join(OUTPUT_DIR, "final_rca_report.json")


def build_final_report(rca_report: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add retrieved knowledge to one RCA report.
    """

    incident_type = rca_report.get("incident_type", "Unknown")

    retrieved_docs = retrieve_by_incident_type(incident_type)

    retrieved_sources = []

    for doc in retrieved_docs:
        retrieved_sources.append(doc.get("path"))

    retrieval_context = build_retrieval_context(retrieved_docs)

    final_report = {
        "incident_id": rca_report.get("incident_id"),
        "incident_type": incident_type,
        "timestamp": rca_report.get("timestamp"),
        "top_root_cause": rca_report.get("top_root_cause"),
        "all_candidates": rca_report.get("candidates", []),
        "retrieved_sources": retrieved_sources,
        "retrieved_knowledge": retrieval_context
    }

    return final_report


def build_all_final_reports(rca_reports: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Add retrieved knowledge to all RCA reports.
    """

    final_reports = []

    for report in rca_reports:
        final_report = build_final_report(report)
        final_reports.append(final_report)

    return final_reports


def save_final_reports(final_reports: List[Dict[str, Any]]) -> None:
    """
    Save final RCA reports to data/rca/final_rca_report.json.
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

    print("\nRetrieved Sources")
    print("-----------------")

    sources = report.get("retrieved_sources", [])

    if not sources:
        print("No knowledge base sources retrieved.")
    else:
        for source in sources:
            print(f"- {source}")

    print("\nRetrieved Knowledge Preview")
    print("---------------------------")

    knowledge = report.get("retrieved_knowledge", "")

    if knowledge:
        print(knowledge[:1200])
    else:
        print("No retrieved knowledge available.")


def main():
    parser = argparse.ArgumentParser(
        description="Run final AIOpsGraph RCA pipeline with retrieved knowledge"
    )

    parser.add_argument(
        "--save",
        action="store_true",
        help="Save final RCA report to data/rca/final_rca_report.json"
    )

    args = parser.parse_args()

    graph = load_graph()

    rca_reports = analyze_all_incidents(graph)

    if not rca_reports:
        print("No incidents found in graph.")
        return

    final_reports = build_all_final_reports(rca_reports)

    for report in final_reports:
        print_final_report(report)

    if args.save:
        save_final_reports(final_reports)


if __name__ == "__main__":
    main()