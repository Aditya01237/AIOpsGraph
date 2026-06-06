import json
import os
import argparse
from typing import Dict, List, Any


GRAPH_FILE = "data/graph/incident_graph.json"
OUTPUT_DIR = "data/rca"

def load_graph(path: str = GRAPH_FILE) -> Dict[str, Any]:
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Graph file not found: {path}\n"
            "Run: python graph/graph_builder.py"
        )
    with open(path, "r") as f:
        return json.load(f)
    
def get_nodes_by_type(graph: Dict[str, Any], node_type: str) -> List[Dict[str, Any]]:
    return [
        node for node in graph.get("nodes", [])
        if node.get("type") == node_type
    ]

def get_node_by_id(graph: Dict[str, Any], node_id: str) -> Dict[str, Any]:
    for node in graph.get("nodes", []):
        if node.get("id") == node_id:
            return node
    return {}

def get_connected_nodes(graph: Dict[str, Any], source_id: str, relation: str) -> List[Dict[str, Any]]:
    connected_nodes = []
    for edge in graph.get("edges", []):
        if edge.get("source") == source_id and edge.get("relation") == relation:
            target_node = get_node_by_id(graph, edge.get("target"))
            if target_node:
                connected_nodes.append(target_node)

    return connected_nodes

def collect_incident_context(graph: Dict[str, Any], incident: Dict[str, Any]) -> Dict[str, Any]:
    incident_id = incident.get("id")

    pods = get_connected_nodes(graph, incident_id, "AFFECTS")
    events = get_connected_nodes(graph, incident_id, "HAS_EVENT")
    logs = get_connected_nodes(graph, incident_id, "HAS_LOG")
    root_causes = get_connected_nodes(graph, incident_id, "HAS_ROOT_CAUSE_SIGNAL")

    return {
        "incident": incident,
        "pods": pods,
        "events": events,
        "logs": logs,
        "root_causes": root_causes
    }

def text_from_context(context: Dict[str, Any]) -> str:
    parts = []

    incident = context.get("incident", {})
    parts.append(str(incident.get("label", "")))
    parts.append(str(incident.get("properties", {})))

    for pod in context.get("pods", []):
        parts.append(str(pod.get("label", "")))
        parts.append(str(pod.get("properties", {})))

    for event in context.get("events", []):
        parts.append(str(event.get("label", "")))
        parts.append(str(event.get("properties", {})))

    for log in context.get("logs", []):
        parts.append(str(log.get("properties", {})))

    for root in context.get("root_causes", []):
        parts.append(str(root.get("properties", {})))

    return " ".join(parts).lower()

def extract_evidence(context: Dict[str, Any]) -> List[str]:
    evidence = []

    for pod in context.get("pods", []):
        props = pod.get("properties", {})
        evidence.append(
            f"Pod {pod.get('label')} has phase={props.get('phase')}, "
            f"ready={props.get('ready')}, restart_count={props.get('restart_count')}"
        )

        if props.get("state"):
            evidence.append(f"Container current state: {props.get('state')}")

        if props.get("last_state"):
            evidence.append(f"Container last state: {props.get('last_state')}")

    for event in context.get("events", []):
        props = event.get("properties", {})
        evidence.append(
            f"Event reason={props.get('reason')}, message={props.get('message')}"
        )

    for log in context.get("logs", []):
        props = log.get("properties", {})
        excerpt = props.get("log_excerpt")
        if excerpt:
            evidence.append(f"Log excerpt from {props.get('pod_name')}: {excerpt[:300]}")

    return evidence

def crashloop_rules(context: Dict[str, Any]) -> List[Dict[str, Any]]:
    text = text_from_context(context)
    evidence = extract_evidence(context)

    candidates = []

    score = 0.50

    if "crashloopbackoff" in text:
        score += 0.20

    if "restart_count" in text or "restart" in text:
        score += 0.10

    if "terminated" in text:
        score += 0.10

    if "exit_code" in text or "exit code" in text:
        score += 0.05

    if "application crashed" in text or "startup failure" in text:
        score += 0.05

    candidates.append({
        "root_cause": "Application process is repeatedly crashing after startup.",
        "confidence": min(score, 0.95),
        "category": "Application Failure",
        "evidence": evidence,
        "recommended_fix": [
            "Check container startup command and arguments.",
            "Check application logs using kubectl logs --previous.",
            "Verify required environment variables, ConfigMaps, and Secrets.",
            "Check if the app exits due to missing dependency or bad configuration."
        ]
    })

    candidates.append({
        "root_cause": "Missing or invalid runtime configuration may be causing startup failure.",
        "confidence": 0.55,
        "category": "Configuration Issue",
        "evidence": evidence,
        "recommended_fix": [
            "Verify ConfigMap and Secret references.",
            "Check application environment variables.",
            "Compare deployment config with a known working version."
        ]
    })

    return candidates

def imagepull_rules(context: Dict[str, Any]) -> List[Dict[str, Any]]:
    text = text_from_context(context)
    evidence = extract_evidence(context)

    score = 0.60

    if "imagepullbackoff" in text:
        score += 0.20

    if "errimagepull" in text:
        score += 0.10

    if "failed to pull image" in text:
        score += 0.10

    candidates = [
        {
            "root_cause": "Kubernetes cannot pull the container image.",
            "confidence": min(score, 0.98),
            "category": "Image Pull Failure",
            "evidence": evidence,
            "recommended_fix": [
                "Verify image name and tag.",
                "Check whether the image exists in the registry.",
                "If image is private, verify imagePullSecrets.",
                "Check registry connectivity and authentication."
            ]
        },
        {
            "root_cause": "Image tag or registry path may be incorrect.",
            "confidence": 0.70,
            "category": "Invalid Image Reference",
            "evidence": evidence,
            "recommended_fix": [
                "Use docker pull locally to verify the image.",
                "Check spelling of registry, repository, and tag.",
                "Avoid using non-existing or temporary image tags."
            ]
        }
    ]

    return candidates

def oom_rules(context: Dict[str, Any]) -> List[Dict[str, Any]]:
    text = text_from_context(context)
    evidence = extract_evidence(context)

    score = 0.60

    if "oomkilled" in text:
        score += 0.25

    if "exit_code': 137" in text or "exit_code=137" in text or "exit code 137" in text:
        score += 0.10

    if "memory" in text:
        score += 0.05

    candidates = [
        {
            "root_cause": "Container exceeded its memory limit and was killed.",
            "confidence": min(score, 0.98),
            "category": "Resource Limit",
            "evidence": evidence,
            "recommended_fix": [
                "Increase container memory limit.",
                "Check application memory usage and memory leaks.",
                "Add memory monitoring through Prometheus/Grafana.",
                "Tune runtime memory settings such as JVM heap or Python workload size."
            ]
        },
        {
            "root_cause": "Application may have a memory leak or unbounded memory allocation.",
            "confidence": 0.70,
            "category": "Application Memory Issue",
            "evidence": evidence,
            "recommended_fix": [
                "Profile memory usage.",
                "Check recent code changes related to caching or large data loading.",
                "Limit in-memory data structures.",
                "Add memory requests and limits based on observed usage."
            ]
        }
    ]

    return candidates

def unknown_rules(context: Dict[str, Any]) -> List[Dict[str, Any]]:
    evidence = extract_evidence(context)

    return [
        {
            "root_cause": "Unknown incident pattern.",
            "confidence": 0.30,
            "category": "Unknown",
            "evidence": evidence,
            "recommended_fix": [
                "Check pod describe output.",
                "Check Kubernetes events.",
                "Check current and previous logs.",
                "Add a new rule if this pattern appears frequently."
            ]
        }
    ]

def rank_candidates(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(
        candidates,
        key=lambda item: item.get("confidence", 0),
        reverse=True
    )

def analyze_incident(context: Dict[str, Any]) -> Dict[str, Any]:
    incident = context.get("incident", {})
    incident_type = incident.get("label", "Unknown")

    if incident_type == "CrashLoopBackOff":
        candidates = crashloop_rules(context)
    elif incident_type == "ImagePullBackOff":
        candidates = imagepull_rules(context)
    elif incident_type == "OOMKilled":
        candidates = oom_rules(context)
    else:
        candidates = unknown_rules(context)

    ranked_candidates = rank_candidates(candidates)

    return {
        "incident_id": incident.get("id"),
        "incident_type": incident_type,
        "timestamp": incident.get("properties", {}).get("timestamp"),
        "top_root_cause": ranked_candidates[0] if ranked_candidates else None,
        "candidates": ranked_candidates
    }

def analyze_all_incidents(graph: Dict[str, Any]) -> List[Dict[str, Any]]:
    incidents = get_nodes_by_type(graph, "Incident")

    reports = []

    for incident in incidents:
        context = collect_incident_context(graph, incident)
        report = analyze_incident(context)
        reports.append(report)

    return reports

def save_reports(reports: List[Dict[str, Any]]) -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    output_file = os.path.join(OUTPUT_DIR, "rca_report.json")

    with open(output_file, "w") as f:
        json.dump(reports, f, indent=2)

    print(f"Saved RCA report: {output_file}")

def print_report(report: Dict[str, Any]) -> None:
    print("\nRCA Report")
    print("==========")
    print(f"Incident ID: {report.get('incident_id')}")
    print(f"Incident Type: {report.get('incident_type')}")
    print(f"Timestamp: {report.get('timestamp')}")

    top = report.get("top_root_cause")

    if not top:
        print("No root cause candidate found.")
        return

    print("\nTop Root Cause")
    print("--------------")
    print(f"Cause: {top.get('root_cause')}")
    print(f"Category: {top.get('category')}")
    print(f"Confidence: {top.get('confidence')}")

    print("\nRecommended Fix")
    print("---------------")
    for fix in top.get("recommended_fix", []):
        print(f"- {fix}")

    print("\nEvidence")
    print("--------")
    for item in top.get("evidence", [])[:5]:
        print(f"- {item}")

def main():
    parser = argparse.ArgumentParser(description="Run RCA rules on AIOpsGraph incident graph")

    parser.add_argument(
        "--save",
        action="store_true",
        help="Save RCA report to data/rca/rca_report.json"
    )

    args = parser.parse_args()

    graph = load_graph()
    reports = analyze_all_incidents(graph)

    if not reports:
        print("No incidents found in graph.")
        return

    for report in reports:
        print_report(report)

    if args.save:
        save_reports(reports)

if __name__ == "__main__":
    main()