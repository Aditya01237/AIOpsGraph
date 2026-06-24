import os
import re
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
            "Run this first: python3 rca_engine/run_rca.py --save"
        )

    with open(path, "r") as f:
        return json.load(f)


def safe_text(value: Any) -> str:
    if value is None:
        return "N/A"

    return str(value)


def escape_table_text(value: Any) -> str:
    text = safe_text(value)
    text = text.replace("|", "\\|")
    text = text.replace("\n", " ")
    return text


def select_latest_reports(
    reports: List[Dict[str, Any]],
    latest_count: int
) -> List[Dict[str, Any]]:
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


def add_bullets(lines: List[str], items: List[str]) -> None:
    if not items:
        lines.append("- N/A")
        lines.append("")
        return

    for item in items:
        lines.append(f"- {item}")

    lines.append("")


def short_text(text: str, max_len: int = 180) -> str:
    text = safe_text(text).strip()

    if len(text) <= max_len:
        return text

    return text[:max_len].rstrip() + "..."


def extract_regex(text: str, pattern: str) -> str:
    match = re.search(pattern, text, re.DOTALL)

    if not match:
        return ""

    return match.group(1).strip()


def clean_log_excerpt(log_text: str) -> str:
    cleaned_lines = []

    for line in log_text.splitlines():
        line = line.strip()

        if line:
            cleaned_lines.append(line)

    if not cleaned_lines:
        return "Previous logs were captured."

    if len(cleaned_lines) <= 2:
        return " | ".join(cleaned_lines)

    return " | ".join(cleaned_lines[-3:])


def clean_evidence_item(item: Any) -> str:
    """
    Convert raw evidence strings into readable report bullets.
    """
    text = safe_text(item).strip()

    pod_match = re.search(
        r"Pod\s+(.+?)\s+has phase=(.*?),\s+ready=(.*?),\s+restart_count=(\d+)",
        text,
        re.DOTALL
    )

    if pod_match:
        pod_name = pod_match.group(1).strip()
        phase = pod_match.group(2).strip()
        ready = pod_match.group(3).strip()
        restart_count = pod_match.group(4).strip()

        if ready == "False":
            return (
                f"Pod `{pod_name}` is not ready. "
                f"Phase is `{phase}` and restart count is `{restart_count}`."
            )

        return (
            f"Pod `{pod_name}` has phase `{phase}`, "
            f"ready status `{ready}`, and restart count `{restart_count}`."
        )

    if text.startswith("Container current state:"):
        reason = extract_regex(text, r"'reason':\s*'([^']+)'")

        if reason:
            return f"Current container state reason is `{reason}`."

        if "waiting" in text.lower():
            return "Current container state is `Waiting`."

        if "running" in text.lower():
            return "Current container state is `Running`."

        return "Current container state was captured."

    if text.startswith("Container last state:"):
        exit_code = extract_regex(text, r"'exit_code':\s*(\d+)")
        reason = extract_regex(text, r"'reason':\s*'([^']+)'")

        parts = []

        if reason:
            parts.append(f"last state reason is `{reason}`")

        if exit_code:
            parts.append(f"exit code is `{exit_code}`")

        if parts:
            return "Container " + " and ".join(parts) + "."

        if "terminated" in text.lower():
            return "Container previous state was `Terminated`."

        return "Container last state was captured."

    event_match = re.search(
        r"Event reason=(.*?),\s+message=(.*)",
        text,
        re.DOTALL
    )

    if event_match:
        reason = event_match.group(1).strip()
        message = short_text(event_match.group(2).strip(), 180)

        return f"Kubernetes event reason is `{reason}` with message: {message}"

    log_match = re.search(
        r"Log excerpt from\s+(.+?):\s*(.*)",
        text,
        re.DOTALL
    )

    if log_match:
        pod_name = log_match.group(1).strip()
        log_text = clean_log_excerpt(log_match.group(2))

        return f"Previous logs from `{pod_name}` show: {log_text}"

    return short_text(text, 220)


def clean_evidence_items(
    evidence: List[Any],
    limit: int = 8
) -> List[str]:
    cleaned = []
    seen = set()

    for item in evidence:
        cleaned_item = clean_evidence_item(item)

        if cleaned_item in seen:
            continue

        cleaned.append(cleaned_item)
        seen.add(cleaned_item)

        if len(cleaned) >= limit:
            break

    return cleaned


def clean_fix_text(fix: Any) -> str:
    text = safe_text(fix)

    text = text.replace("kubectl logs --previous", "`kubectl logs --previous`")
    text = text.replace("ConfigMaps", "`ConfigMaps`")
    text = text.replace("Secrets", "`Secrets`")
    text = text.replace("imagePullSecrets", "`imagePullSecrets`")

    return text


def build_summary_table(lines: List[str], reports: List[Dict[str, Any]]) -> None:
    add_heading(lines, "Summary", 2)

    lines.append("| # | Incident Type | Top Root Cause | Confidence |")
    lines.append("|---|---------------|----------------|------------|")

    for index, report in enumerate(reports, start=1):
        top = report.get("top_root_cause") or {}

        incident_type = escape_table_text(report.get("incident_type"))
        cause = escape_table_text(top.get("root_cause"))
        confidence = escape_table_text(top.get("confidence"))

        lines.append(
            f"| {index} | {incident_type} | {cause} | {confidence} |"
        )

    lines.append("")


def build_retrieved_chunks_section(
    lines: List[str],
    report: Dict[str, Any],
    chunk_limit: int
) -> None:
    chunks = report.get("retrieved_chunks", [])

    if not chunks:
        return

    add_heading(lines, "Top Semantic Matches", 3)

    for chunk in chunks[:chunk_limit]:
        rank = safe_text(chunk.get("rank"))
        score = safe_text(chunk.get("score"))
        source = safe_text(chunk.get("source_path"))
        section = safe_text(chunk.get("section_title"))

        lines.append(
            f"- Rank `{rank}`, score `{score}` from "
            f"`{source}` section `{section}`"
        )

    lines.append("")


def build_knowledge_preview(
    lines: List[str],
    report: Dict[str, Any],
    max_chars: int
) -> None:
    knowledge = report.get("retrieved_knowledge", "")

    if not knowledge:
        return

    add_heading(lines, "Retrieved Knowledge Preview", 3)

    lines.append("```txt")
    lines.append(knowledge[:max_chars].strip())
    lines.append("```")
    lines.append("")


def build_single_report(
    lines: List[str],
    report: Dict[str, Any],
    index: int,
    evidence_limit: int,
    include_chunks: bool,
    chunk_limit: int,
    include_knowledge: bool,
    max_knowledge_chars: int
) -> None:
    incident_type = safe_text(report.get("incident_type"))
    incident_id = safe_text(report.get("incident_id"))
    timestamp = safe_text(report.get("timestamp"))
    retrieval_type = safe_text(report.get("retrieval_type", "semantic"))

    top = report.get("top_root_cause") or {}

    add_heading(lines, f"Incident {index}: {incident_type}", 2)

    lines.append(f"**Incident ID:** `{incident_id}`")
    lines.append("")
    lines.append(f"**Timestamp:** {timestamp}")
    lines.append("")
    lines.append(f"**Retrieval Type:** `{retrieval_type}`")
    lines.append("")

    add_heading(lines, "Root Cause", 3)

    lines.append(f"**Cause:** {safe_text(top.get('root_cause'))}")
    lines.append("")
    lines.append(f"**Category:** {safe_text(top.get('category'))}")
    lines.append("")
    lines.append(f"**Confidence:** `{safe_text(top.get('confidence'))}`")
    lines.append("")

    add_heading(lines, "Clean Evidence", 3)

    raw_evidence = top.get("evidence", [])
    clean_evidence = clean_evidence_items(
        evidence=raw_evidence,
        limit=evidence_limit
    )

    add_bullets(lines, clean_evidence)

    add_heading(lines, "Recommended Fixes", 3)

    fixes = [
        clean_fix_text(fix)
        for fix in top.get("recommended_fix", [])
    ]

    add_bullets(lines, fixes)

    add_heading(lines, "Retrieved Knowledge Sources", 3)

    sources = report.get("retrieved_sources", [])

    if not sources:
        lines.append("- N/A")
    else:
        for source in sources:
            lines.append(f"- `{source}`")

    lines.append("")

    if include_chunks:
        build_retrieved_chunks_section(
            lines=lines,
            report=report,
            chunk_limit=chunk_limit
        )

    if include_knowledge:
        build_knowledge_preview(
            lines=lines,
            report=report,
            max_chars=max_knowledge_chars
        )

    lines.append("---")
    lines.append("")


def build_markdown_report(
    reports: List[Dict[str, Any]],
    latest_count: int,
    evidence_limit: int,
    include_chunks: bool,
    chunk_limit: int,
    include_knowledge: bool,
    max_knowledge_chars: int
) -> str:
    selected_reports = select_latest_reports(
        reports=reports,
        latest_count=latest_count
    )

    lines = []

    add_heading(lines, "AIOpsGraph RCA Report", 1)

    lines.append(
        "Compact RCA report generated from Kubernetes evidence, graph context, "
        "rule-based RCA, and semantic troubleshooting retrieval."
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
            evidence_limit=evidence_limit,
            include_chunks=include_chunks,
            chunk_limit=chunk_limit,
            include_knowledge=include_knowledge,
            max_knowledge_chars=max_knowledge_chars
        )

    return "\n".join(lines)


def save_markdown(content: str, output_file: str) -> None:
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    with open(output_file, "w") as f:
        f.write(content)

    print(f"Saved clean Markdown RCA report: {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Convert final RCA JSON report into clean Markdown"
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
        help="Number of latest incidents to include"
    )

    parser.add_argument(
        "--evidence-limit",
        type=int,
        default=8,
        help="Maximum evidence bullets to show"
    )

    parser.add_argument(
        "--include-chunks",
        action="store_true",
        help="Include top semantic chunk matches"
    )

    parser.add_argument(
        "--chunk-limit",
        type=int,
        default=3,
        help="Maximum semantic chunk matches to show"
    )

    parser.add_argument(
        "--include-knowledge",
        action="store_true",
        help="Include retrieved knowledge preview"
    )

    parser.add_argument(
        "--max-knowledge-chars",
        type=int,
        default=1000,
        help="Maximum retrieved knowledge characters"
    )

    args = parser.parse_args()

    reports = load_json(args.input)

    markdown = build_markdown_report(
        reports=reports,
        latest_count=args.latest,
        evidence_limit=args.evidence_limit,
        include_chunks=args.include_chunks,
        chunk_limit=args.chunk_limit,
        include_knowledge=args.include_knowledge,
        max_knowledge_chars=args.max_knowledge_chars
    )

    save_markdown(markdown, args.output)


if __name__ == "__main__":
    main()