import os
import re
import glob
import json
from typing import Dict, List, Any


RAW_DIR = "data/raw"
PROCESSED_DIR = "data/processed"


IMPORTANT_EVENT_KEYWORDS = [
    "backoff",
    "back-off",
    "failed",
    "errimagepull",
    "imagepullbackoff",
    "failed to pull image",
    "back-off pulling image",
    "pull access denied",
    "manifest unknown",
    "oomkilled",
    "killing",
    "unhealthy",
]


def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r") as f:
        return json.load(f)


def save_json(data: Dict[str, Any], path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)

    with open(path, "w") as f:
        json.dump(data, f, indent=2)

    print(f"Saved processed incident: {path}")


def safe_lower(value: Any) -> str:
    if value is None:
        return ""
    return str(value).lower()


def contains_any(text: str, keywords: List[str]) -> bool:
    text = safe_lower(text)

    for keyword in keywords:
        if keyword in text:
            return True

    return False


def get_exit_code(text: str) -> int:
    """
    Extract exit code from Kubernetes state text.

    Example text:
    'exit_code': 137
    exit code 1
    exit_code=1
    """
    text = safe_lower(text)

    patterns = [
        r"exit_code['\"\s:=]+(\d+)",
        r"exit code\s+(\d+)",
        r"exitcode['\"\s:=]+(\d+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)

        if match:
            return int(match.group(1))

    return -1


def get_pod_labels(pod: Dict[str, Any]) -> Dict[str, Any]:
    labels = pod.get("labels")

    if isinstance(labels, dict):
        return labels

    return {}


def get_event_object_name(event: Dict[str, Any]) -> str:
    return (
        event.get("involved_object_name")
        or event.get("object_name")
        or ""
    )


def get_event_text(event: Dict[str, Any]) -> str:
    return " ".join([
        safe_lower(event.get("type")),
        safe_lower(event.get("reason")),
        safe_lower(event.get("message")),
        safe_lower(get_event_object_name(event)),
    ])


def event_belongs_to_pod(event: Dict[str, Any], pod_name: str) -> bool:
    object_name = get_event_object_name(event)

    if not object_name or not pod_name:
        return False

    if object_name == pod_name:
        return True

    if object_name.startswith(pod_name):
        return True

    if pod_name.startswith(object_name):
        return True

    return False


def get_events_for_pod(snapshot: Dict[str, Any], pod_name: str) -> List[Dict[str, Any]]:
    matched_events = []

    for event in snapshot.get("events", []):
        if event_belongs_to_pod(event, pod_name):
            matched_events.append(event)

    return matched_events


def get_logs_for_pod(snapshot: Dict[str, Any], pod_name: str) -> Dict[str, Any]:
    for log in snapshot.get("logs", []):
        if log.get("pod_name") == pod_name:
            return log

    return {}


def build_container_text(
    pod: Dict[str, Any],
    container_status: Dict[str, Any],
    pod_events: List[Dict[str, Any]],
    pod_logs: Dict[str, Any]
) -> str:
    parts = []

    parts.append(safe_lower(pod.get("pod_name")))
    parts.append(safe_lower(pod.get("phase")))

    labels = get_pod_labels(pod)
    parts.append(safe_lower(labels))

    parts.append(safe_lower(container_status.get("container_name")))
    parts.append(safe_lower(container_status.get("image")))
    parts.append(safe_lower(container_status.get("state")))
    parts.append(safe_lower(container_status.get("last_state")))
    parts.append(safe_lower(container_status.get("restart_count")))
    parts.append(safe_lower(container_status.get("ready")))

    for event in pod_events:
        parts.append(get_event_text(event))

    parts.append(safe_lower(pod_logs.get("current_logs")))
    parts.append(safe_lower(pod_logs.get("previous_logs")))
    parts.append(safe_lower(pod_logs.get("current_log_error")))
    parts.append(safe_lower(pod_logs.get("previous_log_error")))

    return " ".join(parts)


def detect_container_incident_type(
    pod: Dict[str, Any],
    container_status: Dict[str, Any],
    pod_events: List[Dict[str, Any]],
    pod_logs: Dict[str, Any]
) -> str:
    """
    Detect incident type using pod-specific evidence only.

    This avoids stale old namespace events from changing the incident type.
    """
    text = build_container_text(
        pod=pod,
        container_status=container_status,
        pod_events=pod_events,
        pod_logs=pod_logs
    )

    exit_code = get_exit_code(text)

    if "oomkilled" in text or exit_code == 137:
        return "OOMKilled"

    if (
        "imagepullbackoff" in text
        or "errimagepull" in text
        or "failed to pull image" in text
        or "back-off pulling image" in text
        or "pull access denied" in text
        or "manifest unknown" in text
    ):
        return "ImagePullBackOff"

    if (
        "crashloopbackoff" in text
        or "back-off restarting failed container" in text
    ):
        return "CrashLoopBackOff"

    restart_count = container_status.get("restart_count") or 0
    ready = container_status.get("ready")

    if ready is False and restart_count > 0:
        return "CrashLoopBackOff"

    if exit_code > 0:
        return "CrashLoopBackOff"

    return "Unknown"


def is_container_affected(
    pod: Dict[str, Any],
    container_status: Dict[str, Any],
    pod_events: List[Dict[str, Any]],
    pod_logs: Dict[str, Any]
) -> bool:
    """
    Decide whether a container is actually affected.

    Important:
    We should not mark healthy pods as affected just because the string contains:
    waiting: None
    terminated: None
    """
    ready = container_status.get("ready")
    restart_count = container_status.get("restart_count") or 0

    text = build_container_text(
        pod=pod,
        container_status=container_status,
        pod_events=pod_events,
        pod_logs=pod_logs
    )

    exit_code = get_exit_code(text)

    strong_failure_keywords = [
        "crashloopbackoff",
        "back-off restarting failed container",
        "imagepullbackoff",
        "errimagepull",
        "failed to pull image",
        "back-off pulling image",
        "oomkilled",
        "pull access denied",
        "manifest unknown",
    ]

    if contains_any(text, strong_failure_keywords):
        return True

    if exit_code > 0:
        return True

    if ready is False and restart_count > 0:
        return True

    if ready is False and contains_any(text, ["waiting", "failed", "backoff"]):
        return True

    return False


def extract_affected_pods(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    affected_pods = []

    for pod in snapshot.get("pods", []):
        pod_name = pod.get("pod_name", "unknown_pod")
        labels = get_pod_labels(pod)

        pod_events = get_events_for_pod(snapshot, pod_name)
        pod_logs = get_logs_for_pod(snapshot, pod_name)

        for container_status in pod.get("container_statuses", []):
            if not is_container_affected(
                pod=pod,
                container_status=container_status,
                pod_events=pod_events,
                pod_logs=pod_logs
            ):
                continue

            detected_type = detect_container_incident_type(
                pod=pod,
                container_status=container_status,
                pod_events=pod_events,
                pod_logs=pod_logs
            )

            affected_pods.append({
                "pod_name": pod_name,
                "app": labels.get("app"),
                "incident_label": labels.get("incident"),
                "detected_incident_type": detected_type,
                "phase": pod.get("phase"),
                "container_name": container_status.get("container_name"),
                "image": container_status.get("image"),
                "ready": container_status.get("ready"),
                "restart_count": container_status.get("restart_count"),
                "state": container_status.get("state"),
                "last_state": container_status.get("last_state"),
            })

    return affected_pods


def score_incident_types(affected_pods: List[Dict[str, Any]]) -> Dict[str, int]:
    scores = {
        "CrashLoopBackOff": 0,
        "ImagePullBackOff": 0,
        "OOMKilled": 0,
        "Unknown": 0,
    }

    for pod in affected_pods:
        detected_type = pod.get("detected_incident_type", "Unknown")
        restart_count = pod.get("restart_count") or 0

        if detected_type not in scores:
            detected_type = "Unknown"

        scores[detected_type] += 100

        if detected_type == "CrashLoopBackOff":
            scores[detected_type] += min(restart_count, 30)

        if detected_type == "OOMKilled":
            scores[detected_type] += 20

        if detected_type == "ImagePullBackOff":
            scores[detected_type] += 20

    return scores


def detect_incident_type(
    snapshot: Dict[str, Any],
    affected_pods: List[Dict[str, Any]]
) -> str:
    """
    Detect incident type mainly from affected pods.

    This fixes the old bug where stale namespace events caused wrong detection.
    """
    if affected_pods:
        scores = score_incident_types(affected_pods)

        best_type = max(scores, key=scores.get)

        if scores[best_type] > 0 and best_type != "Unknown":
            return best_type

    fallback_text = safe_lower(snapshot)

    if "oomkilled" in fallback_text or "exit_code': 137" in fallback_text:
        return "OOMKilled"

    if "crashloopbackoff" in fallback_text or "back-off restarting failed container" in fallback_text:
        return "CrashLoopBackOff"

    if "imagepullbackoff" in fallback_text or "errimagepull" in fallback_text:
        return "ImagePullBackOff"

    return "Unknown"


def filter_primary_affected_pods(
    affected_pods: List[Dict[str, Any]],
    incident_type: str
) -> List[Dict[str, Any]]:
    """
    Keep only pods related to the selected primary incident type.

    This prevents CrashLoopBackOff evidence from appearing inside
    ImagePullBackOff report and vice versa.
    """
    if incident_type == "Unknown":
        return affected_pods

    filtered = [
        pod for pod in affected_pods
        if pod.get("detected_incident_type") == incident_type
    ]

    if filtered:
        return filtered

    return affected_pods


def extract_important_events(
    snapshot: Dict[str, Any],
    affected_pods: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    important_events = []

    affected_pod_names = {
        pod.get("pod_name")
        for pod in affected_pods
        if pod.get("pod_name")
    }

    for event in snapshot.get("events", []):
        event_text = get_event_text(event)

        if not contains_any(event_text, IMPORTANT_EVENT_KEYWORDS):
            continue

        object_name = get_event_object_name(event)

        if affected_pod_names:
            belongs_to_affected_pod = False

            for pod_name in affected_pod_names:
                if event_belongs_to_pod(event, pod_name):
                    belongs_to_affected_pod = True
                    break

            if not belongs_to_affected_pod:
                continue

        important_events.append({
            "type": event.get("type"),
            "reason": event.get("reason"),
            "message": event.get("message"),
            "object_kind": event.get("involved_object_kind"),
            "object_name": object_name,
            "count": event.get("count"),
            "last_timestamp": event.get("last_timestamp"),
        })

    return important_events


def extract_important_logs(
    snapshot: Dict[str, Any],
    affected_pods: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    important_logs = []

    affected_pod_names = {
        pod.get("pod_name")
        for pod in affected_pods
        if pod.get("pod_name")
    }

    for log in snapshot.get("logs", []):
        pod_name = log.get("pod_name")

        if affected_pod_names and pod_name not in affected_pod_names:
            continue

        previous_logs = log.get("previous_logs") or ""
        current_logs = log.get("current_logs") or ""

        selected_logs = previous_logs if previous_logs.strip() else current_logs

        if not selected_logs.strip():
            continue

        important_logs.append({
            "pod_name": pod_name,
            "log_excerpt": selected_logs[-1000:],
        })

    return important_logs


def infer_root_cause_signal(incident_type: str) -> str:
    if incident_type == "CrashLoopBackOff":
        return "Container process is repeatedly crashing after startup."

    if incident_type == "ImagePullBackOff":
        return "Kubernetes cannot pull the container image."

    if incident_type == "OOMKilled":
        return "Container exceeded its memory limit and was killed."

    return "Unknown root cause signal."


def build_processed_incident(
    snapshot: Dict[str, Any],
    source_file: str
) -> Dict[str, Any]:
    all_affected_pods = extract_affected_pods(snapshot)

    incident_type = detect_incident_type(
        snapshot=snapshot,
        affected_pods=all_affected_pods
    )

    primary_affected_pods = filter_primary_affected_pods(
        affected_pods=all_affected_pods,
        incident_type=incident_type
    )

    important_events = extract_important_events(
        snapshot=snapshot,
        affected_pods=primary_affected_pods
    )

    important_logs = extract_important_logs(
        snapshot=snapshot,
        affected_pods=primary_affected_pods
    )

    processed_incident = {
        "snapshot_id": snapshot.get("snapshot_id"),
        "timestamp": snapshot.get("timestamp"),
        "namespace": snapshot.get("namespace"),
        "source_file": source_file,
        "incident_type": incident_type,
        "root_cause_signal": infer_root_cause_signal(incident_type),
        "affected_pods": primary_affected_pods,
        "all_affected_pods_count": len(all_affected_pods),
        "important_events": important_events,
        "important_logs": important_logs,
    }

    return processed_incident


def process_file(path: str) -> None:
    snapshot = load_json(path)

    processed_incident = build_processed_incident(
        snapshot=snapshot,
        source_file=os.path.basename(path)
    )

    snapshot_id = snapshot.get("snapshot_id", "unknown_snapshot")
    output_file = os.path.join(
        PROCESSED_DIR,
        f"processed_{snapshot_id}.json"
    )

    save_json(processed_incident, output_file)

    print("Incident Summary")
    print("----------------")
    print(f"Source: {os.path.basename(path)}")
    print(f"Detected Incident Type: {processed_incident['incident_type']}")
    print(f"Affected Pods Used: {len(processed_incident['affected_pods'])}")
    print(f"All Affected Pods Found: {processed_incident['all_affected_pods_count']}")
    print(f"Important Events: {len(processed_incident['important_events'])}")
    print(f"Important Logs: {len(processed_incident['important_logs'])}")
    print()


def main():
    raw_files = glob.glob(os.path.join(RAW_DIR, "*.json"))

    if not raw_files:
        print("No raw incident snapshots found.")
        print("Run: python3 collector/k8s_collector.py")
        return

    raw_files.sort()

    for path in raw_files:
        process_file(path)


if __name__ == "__main__":
    main()