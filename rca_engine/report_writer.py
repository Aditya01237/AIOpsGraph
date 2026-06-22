import os
import json
import argparse
from typing import Dict, List, Any


INPUT_FILE = "data/rca/final_rca_report.json"
OUTPUT_DIR = "data/reports"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "final_rca_report.md")


def load_json(path: str) -> List[Dict[str, Any]]:
    """
    Load final RCA JSON report.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Input report not found: {path}\n"
            "Run this first: python rca_engine/run_rca.py --save"
        )

    with open(path, "r") as f:
        return json.load(f)


def safe_text(value: Any) -> str:
    """
    Convert None or complex values into safe text.
    """
    if value is None:
        return "N/A"

    return str(value)


def write_heading(lines: List[str], text: str, level: int = 1) -> None:
    """
    Add markdown heading.
    """
    lines.append(f"{'#' * level} {text}")
    lines.append("")


def write_bullet_list(lines: List[str], items: List[Any]) -> None:
    """
    Add markdown bullet list.
    """
    if not items:
        lines.append("- N/A")
        lines.append("")
        return

    for item in items:
        lines.append(f"- {safe_text(item)}")

    lines.append("")


def format_top_root_cause(top: Dict[str, Any]) -> List[str]:
    """
    Convert top root cause into markdown lines.
    """
    lines = []

    if not top:
        lines.append("No root cause candidate found.")
        lines.append("")
        return lines

    lines.append(f"**Cause:** {safe_text(top.get('root_cause'))}")
    lines.append("")
    lines.append(f"**Category:** {safe_text(top.get('category'))}")
    lines.append("")
    lines.append(f"**Confidence:** {safe_text(top.get('confidence'))}")
    lines.append("")

    write_heading(lines, "Evidence", 3)
    write_bullet_list(lines, top.get("evidence", [])[:10])

    write_heading(lines, "Recommended Fixes", 3)
    write_bullet_list(lines, top.get("recommended_fix", []))

    return lines


def format_all_candidates(candidates: List[Dict[str, Any]]) -> List[str]:
    """
    Convert all root cause candidates into markdown.
    """
    lines = []

    if not candidates:
        lines.append("No candidates found.")
        lines.append("")
        return lines

    for index, candidate in enumerate(candidates, start=1):
        lines.append(f"### Candidate {index}")
        lines.append("")
        lines.append(f"**Root Cause:** {safe_text(candidate.get('root_cause'))}")
        lines.append("")
        lines.append(f"**Category:** {safe_text(candidate.get('category'))}")
        lines.append("")
        lines.append(f"**Confidence:** {safe_text(candidate.get('confidence'))}")
        lines.append("")
        lines.append("**Fixes:**")
        lines.append("")

        fixes = candidate.get("recommended_fix", [])
        if fixes:
            for fix in fixes:
                lines.append(f"- {fix}")
        else:
            lines.append("- N/A")

        lines.append("")

    return lines


def format_retrieved_sources(sources: List[str]) -> List[str]:
    """
    Convert retrieved source paths into markdown.
    """
    lines = []

    if not sources:
        lines.append("- No sources retrieved")
        lines.append("")
        return lines

    for source in sources:
        lines.append(f"- `{source}`")

    lines.append("")
    return lines


def format_retrieved_knowledge(knowledge: str, max_chars: int = 3000) -> List[str]:
    """
    Add retrieved knowledge preview.
    """
    lines = []

    if not knowledge:
        lines.append("No retrieved knowledge available.")
        lines.append("")
        return lines

    preview = knowledge[:max_chars]

    lines.append("```txt")
    lines.append(preview)
    lines.append("```")
    lines.append("")

    return lines


def build_single_report(report: Dict[str, Any], index: int) -> List[str]:
    """
    Build markdown for one incident RCA report.
    """
    lines = []

    incident_type = report.get("incident_type", "Unknown")
    incident_id = report.get("incident_id", "Unknown")

    write_heading(lines, f"Incident {index}: {incident_type}", 2)

    lines.append(f"**Incident ID:** `{safe_text(incident_id)}`")
    lines.append("")
    lines.append(f"**Incident Type:** {safe_text(incident_type)}")
    lines.append("")
    lines.append(f"**Timestamp:** {safe_text(report.get('timestamp'))}")
    lines.append("")

    write_heading(lines, "Top Root Cause", 3)
    lines.extend(format_top_root_cause(report.get("top_root_cause", {})))

    write_heading(lines, "All Root Cause Candidates", 3)
    lines.extend(format_all_candidates(report.get("all_candidates", [])))

    write_heading(lines, "Retrieved Knowledge Sources", 3)
    lines.extend(format_retrieved_sources(report.get("retrieved_sources", [])))

    write_heading(lines, "Retrieved Knowledge Preview", 3)
    lines.extend(format_retrieved_knowledge(report.get("retrieved_knowledge", "")))

    lines.append("---")
    lines.append("")

    return lines


def build_markdown_report(reports: List[Dict[str, Any]]) -> str:
    """
    Build complete markdown RCA report.
    """
    lines = []

    write_heading(lines, "AIOpsGraph RCA Report", 1)

    lines.append("This report was generated from Kubernetes incident evidence, graph context, RCA rules, and retrieved troubleshooting knowledge.")
    lines.append("")

    write_heading(lines, "Summary", 2)

    lines.append(f"**Total Incidents Analyzed:** {len(reports)}")
    lines.append("")

    if not reports:
        lines.append("No incidents found.")
        lines.append("")
        return "\n".join(lines)

    for index, report in enumerate(reports, start=1):
        incident_type = report.get("incident_type", "Unknown")
        top = report.get("top_root_cause", {})
        cause = top.get("root_cause", "N/A") if top else "N/A"
        confidence = top.get("confidence", "N/A") if top else "N/A"

        lines.append(f"- **Incident {index}:** {incident_type}")
        lines.append(f"  - Root Cause: {cause}")
        lines.append(f"  - Confidence: {confidence}")

    lines.append("")

    write_heading(lines, "Detailed RCA", 2)

    for index, report in enumerate(reports, start=1):
        lines.extend(build_single_report(report, index))

    return "\n".join(lines)


def save_markdown(content: str, output_file: str = OUTPUT_FILE) -> None:
    """
    Save markdown report.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with open(output_file, "w") as f:
        f.write(content)

    print(f"Saved Markdown RCA report: {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Convert final RCA JSON report into Markdown"
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

    args = parser.parse_args()

    reports = load_json(args.input)
    markdown = build_markdown_report(reports)
    save_markdown(markdown, args.output)


if __name__ == "__main__":
    main()