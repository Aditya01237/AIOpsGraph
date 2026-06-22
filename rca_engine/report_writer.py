import os
import json
import argparse
from typing import Dict, List, Any


INPUT_FILE = "data/rca/final_rca_report.json"
OUTPUT_DIR = "data/reports"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "final_rca_report.md")


def load_json(path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Input report not found: {path}\n"
            "Run this first: python rca_engine/run_rca.py --save"
        )

    with open(path, "r") as f:
        return json.load(f)


def safe_text(value: Any) -> str:
    if value is None:
        return "N/A"
    return str(value)


def select_latest_reports(
    reports: List[Dict[str, Any]],
    latest_count: int
) -> List[Dict[str, Any]]:
    """
    Keep only latest N reports.

    This prevents the Markdown file from becoming too large
    when old incident snapshots are also present.
    """
    if latest_count <= 0:
        return reports

    sorted_reports = sorted(
        reports,
        key=lambda report: safe_text(report.get("timestamp")),
        reverse=True
    )

    return sorted_reports[:latest_count]


def add_heading(lines: List[str], text: str, level: int) -> None:
    lines.append(f"{'#' * level} {text}")
    lines.append("")


def add_bullets(lines: List[str], items: List[Any], limit: int = 5) -> None:
    if not items:
        lines.append("- N/A")
        lines.append("")
        return

    for item in items[:limit]:
        lines.append(f"- {safe_text(item)}")

    if len(items) > limit:
        lines.append(f"- ... {len(items) - limit} more items hidden")

    lines.append("")


def build_summary_table(lines: List[str], reports: List[Dict[str, Any]]) -> None:
    add_heading(lines, "Summary", 2)

    lines.append("| # | Incident Type | Top Root Cause | Confidence |")
    lines.append("|---|---------------|----------------|------------|")

    for index, report in enumerate(reports, start=1):
        top = report.get("top_root_cause") or {}

        incident_type = safe_text(report.get("incident_type"))
        cause = safe_text(top.get("root_cause"))
        confidence = safe_text(top.get("confidence"))

        lines.append(
            f"| {index} | {incident_type} | {cause} | {confidence} |"
        )

    lines.append("")


def build_single_report(
    lines: List[str],
    report: Dict[str, Any],
    index: int,
    include_knowledge: bool,
    max_knowledge_chars: int
) -> None:
    incident_type = safe_text(report.get("incident_type"))
    incident_id = safe_text(report.get("incident_id"))
    timestamp = safe_text(report.get("timestamp"))

    top = report.get("top_root_cause") or {}

    add_heading(lines, f"Incident {index}: {incident_type}", 2)

    lines.append(f"**Incident ID:** `{incident_id}`")
    lines.append("")
    lines.append(f"**Timestamp:** {timestamp}")
    lines.append("")

    add_heading(lines, "Top Root Cause", 3)

    lines.append(f"**Cause:** {safe_text(top.get('root_cause'))}")
    lines.append("")
    lines.append(f"**Category:** {safe_text(top.get('category'))}")
    lines.append("")
    lines.append(f"**Confidence:** {safe_text(top.get('confidence'))}")
    lines.append("")

    add_heading(lines, "Evidence", 3)
    add_bullets(lines, top.get("evidence", []), limit=5)

    add_heading(lines, "Recommended Fixes", 3)
    add_bullets(lines, top.get("recommended_fix", []), limit=6)

    add_heading(lines, "Retrieved Knowledge Sources", 3)
    sources = report.get("retrieved_sources", [])

    if not sources:
        lines.append("- N/A")
    else:
        for source in sources:
            lines.append(f"- `{source}`")

    lines.append("")

    if include_knowledge:
        add_heading(lines, "Retrieved Knowledge Preview", 3)

        knowledge = report.get("retrieved_knowledge", "")

        if knowledge:
            lines.append("```txt")
            lines.append(knowledge[:max_knowledge_chars])
            lines.append("```")
        else:
            lines.append("N/A")

        lines.append("")

    lines.append("---")
    lines.append("")


def build_markdown_report(
    reports: List[Dict[str, Any]],
    latest_count: int,
    include_knowledge: bool,
    max_knowledge_chars: int
) -> str:
    selected_reports = select_latest_reports(reports, latest_count)

    lines = []

    add_heading(lines, "AIOpsGraph RCA Report", 1)

    lines.append(
        "Compact RCA report generated from Kubernetes evidence, graph context, "
        "rule-based RCA, and retrieved troubleshooting knowledge."
    )
    lines.append("")

    lines.append(f"**Total Reports in JSON:** {len(reports)}")
    lines.append("")
    lines.append(f"**Reports Shown in Markdown:** {len(selected_reports)}")
    lines.append("")

    if not selected_reports:
        lines.append("No incidents found.")
        lines.append("")
        return "\n".join(lines)

    build_summary_table(lines, selected_reports)

    add_heading(lines, "Detailed RCA", 2)

    for index, report in enumerate(selected_reports, start=1):
        build_single_report(
            lines=lines,
            report=report,
            index=index,
            include_knowledge=include_knowledge,
            max_knowledge_chars=max_knowledge_chars
        )

    return "\n".join(lines)


def save_markdown(content: str, output_file: str) -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with open(output_file, "w") as f:
        f.write(content)

    print(f"Saved compact Markdown RCA report: {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Convert final RCA JSON report into compact Markdown"
    )

    parser.add_argument(
        "--input",
        type=str,
        default=INPUT_FILE,
        help="Input final RCA JSON report path"
    )

    parser.add_argument(
        "--output",
        type=str,
        default=OUTPUT_FILE,
        help="Output Markdown report path"
    )

    parser.add_argument(
        "--latest",
        type=int,
        default=1,
        help="Number of latest incidents to include in Markdown report"
    )

    parser.add_argument(
        "--include-knowledge",
        action="store_true",
        help="Include retrieved knowledge preview in Markdown report"
    )

    parser.add_argument(
        "--max-knowledge-chars",
        type=int,
        default=800,
        help="Maximum retrieved knowledge characters per incident"
    )

    args = parser.parse_args()

    reports = load_json(args.input)

    markdown = build_markdown_report(
        reports=reports,
        latest_count=args.latest,
        include_knowledge=args.include_knowledge,
        max_knowledge_chars=args.max_knowledge_chars
    )

    save_markdown(markdown, args.output)


if __name__ == "__main__":
    main()