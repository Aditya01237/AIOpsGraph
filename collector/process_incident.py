import json
import os
import glob


RAW_DIR = "data/raw"
PROCESSED_DIR = "data/processed"


def load_json(path):
    with open(path, "r") as f:
        return json.load(f)


def save_json(path, data):
    os.makedirs(PROCESSED_DIR, exist_ok=True)

    with open(path, "w") as f:
        json.dump(data, f, indent=2)

    print(f"Saved processed incident: {path}")


def text_contains(snapshot, keyword):
    """
    Search keyword inside complete snapshot text.
    This is simple but useful for first version.
    """
    snapshot_text = json.dumps(snapshot).lower()
    return keyword.lower() in snapshot_text


def detect_incident_type(snapshot):
    """
    Detect incident type using signals from pod state, events, and logs.
    """

    if text_contains(snapshot, "imagepullbackoff") or text_contains(snapshot, "errimagepull"):
        return "ImagePullBackOff"

    if text_contains(snapshot, "oomkilled"):
        return "OOMKilled"

    if text_contains(snapshot, "crashloopbackoff") or text_contains(snapshot, "back-off restarting failed container"):
        return "CrashLoopBackOff"

    return "Unknown"


def extract_affected_pods(snapshot):
    """
    Extract pods that are unhealthy or have restarts.
    """

    affected_pods = []

    for pod in snapshot.get("pods", []):
        pod_name = pod.get("pod_name")
        phase = pod.get("phase")
        labels = pod.get("labels", {})

        for container in pod.get("container_statuses", []):
            ready = container.get("ready")
            restart_count = container.get("restart_count", 0)
            state = container.get("state", "")
            last_state = container.get("last_state", "")

            is_affected = (
                ready is False
                or restart_count > 0
                or "waiting" in state.lower()
                or "terminated" in last_state.lower()
            )

            if is_affected:
                affected_pods.append({
                    "pod_name": pod_name,
                    "app": labels.get("app"),
                    "incident_label": labels.get("incident"),
                    "phase": phase,
                    "container_name": container.get("container_name"),
                    "image": container.get("image"),
                    "ready": ready,
                    "restart_count": restart_count,
                    "state": state,
                    "last_state": last_state
                })

    return affected_pods


def extract_important_events(snapshot):
    """
    Keep only warning or failure-related Kubernetes events.
    """

    important_keywords = [
        "backoff",
        "back-off",
        "failed",
        "errimagepull",
        "imagepullbackoff",
        "oomkilled",
        "killing",
        "unhealthy"
    ]

    important_events = []

    for event in snapshot.get("events", []):
        reason = event.get("reason", "") or ""
        message = event.get("message", "") or ""
        event_type = event.get("type", "") or ""

        combined = f"{reason} {message} {event_type}".lower()

        if any(keyword in combined for keyword in important_keywords):
            important_events.append({
                "type": event_type,
                "reason": reason,
                "message": message,
                "object_kind": event.get("involved_object_kind"),
                "object_name": event.get("involved_object_name"),
                "count": event.get("count"),
                "last_timestamp": event.get("last_timestamp")
            })

    return important_events


def extract_important_logs(snapshot):
    """
    Extract short useful logs from affected pods.
    """

    important_logs = []

    for log in snapshot.get("logs", []):
        pod_name = log.get("pod_name")

        current_logs = log.get("current_logs") or ""
        previous_logs = log.get("previous_logs") or ""

        selected_log = previous_logs if previous_logs else current_logs

        if selected_log.strip():
            important_logs.append({
                "pod_name": pod_name,
                "log_excerpt": selected_log[-1000:]
            })

    return important_logs


def infer_root_cause_signal(incident_type):
    """
    Give a simple root cause signal based on detected incident type.
    """

    if incident_type == "CrashLoopBackOff":
        return "Container process is repeatedly crashing after startup."

    if incident_type == "ImagePullBackOff":
        return "Kubernetes cannot pull the container image."

    if incident_type == "OOMKilled":
        return "Container exceeded its memory limit and was killed."

    return "Root cause signal is unknown."


def build_processed_incident(snapshot, source_file):
    incident_type = detect_incident_type(snapshot)

    processed = {
        "source_file": source_file,
        "snapshot_id": snapshot.get("snapshot_id"),
        "timestamp": snapshot.get("timestamp"),
        "namespace": snapshot.get("namespace"),
        "incident_type": incident_type,
        "root_cause_signal": infer_root_cause_signal(incident_type),
        "affected_pods": extract_affected_pods(snapshot),
        "important_events": extract_important_events(snapshot),
        "important_logs": extract_important_logs(snapshot)
    }

    return processed


def process_file(path):
    snapshot = load_json(path)
    processed = build_processed_incident(snapshot, path)

    filename = os.path.basename(path).replace("incident_snapshot", "processed_incident")
    output_path = os.path.join(PROCESSED_DIR, filename)

    save_json(output_path, processed)


def main():
    raw_files = glob.glob(os.path.join(RAW_DIR, "*.json"))

    if not raw_files:
        print("No raw incident snapshots found.")
        print("Run: python collector/k8s_collector.py")
        return

    for path in raw_files:
        process_file(path)

    print(f"\nProcessed {len(raw_files)} raw snapshot(s).")


if __name__ == "__main__":
    main()
