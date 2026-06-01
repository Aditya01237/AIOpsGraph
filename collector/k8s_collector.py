from kubernetes import client, config
from datetime import datetime
import json
import os


NAMESPACE = "aiops-demo"
OUTPUT_DIR = "data/raw"


def load_kubernetes_config():
    """
    Load Kubernetes configuration.

    For local development, this uses kubeconfig from your machine.
    If later we run this collector inside a Kubernetes pod,
    it can fall back to in-cluster config.
    """
    try:
        config.load_kube_config()
        print("Loaded local kubeconfig")
    except Exception:
        config.load_incluster_config()
        print("Loaded in-cluster Kubernetes config")


def safe_str(value):
    """
    Convert complex Kubernetes client objects into string safely.
    This prevents JSON serialization errors.
    """
    if value is None:
        return None
    return str(value)


def collect_pods(v1):
    """
    Collect pod-level and container-level status information.

    This is similar to:
    kubectl get pods
    kubectl describe pod
    """
    pods = v1.list_namespaced_pod(namespace=NAMESPACE) # equivalent to: kubectl get pods -n aiops-demo

    pod_data = []

    for pod in pods.items:
        container_statuses = []

        if pod.status.container_statuses:
            for cs in pod.status.container_statuses:
                container_statuses.append({
                    "container_name": cs.name,
                    "image": cs.image,
                    "ready": cs.ready,
                    "restart_count": cs.restart_count,
                    "state": safe_str(cs.state),
                    "last_state": safe_str(cs.last_state),
                    "started": cs.started,
                })

        pod_info = {
            "pod_name": pod.metadata.name,
            "namespace": pod.metadata.namespace,
            "labels": pod.metadata.labels,
            "node_name": pod.spec.node_name,
            "phase": pod.status.phase,
            "pod_ip": pod.status.pod_ip,
            "host_ip": pod.status.host_ip,
            "start_time": safe_str(pod.status.start_time),
            "creation_timestamp": safe_str(pod.metadata.creation_timestamp),
            "container_statuses": container_statuses,
        }

        pod_data.append(pod_info)

    return pod_data


def collect_events(v1):
    """
    Collect Kubernetes events from the namespace.

    This is similar to:
    kubectl get events -n aiops-demo --sort-by=.lastTimestamp
    """
    events = v1.list_namespaced_event(namespace=NAMESPACE) #equivalent to: kubectl get events -n aiops-demo

    event_data = []

    for event in events.items:
        event_info = {
            "event_name": event.metadata.name,
            "namespace": event.metadata.namespace,
            "type": event.type,
            "reason": event.reason,
            "message": event.message,
            "involved_object_kind": event.involved_object.kind,
            "involved_object_name": event.involved_object.name,
            "first_timestamp": safe_str(event.first_timestamp),
            "last_timestamp": safe_str(event.last_timestamp),
            "event_time": safe_str(event.event_time),
            "count": event.count,
            "source": safe_str(event.source),
        }

        event_data.append(event_info)

    return event_data


def collect_logs(v1):
    """
    Collect recent logs from all pods in the namespace.

    This is similar to:
    kubectl logs <pod-name> -n aiops-demo

    For CrashLoopBackOff pods, we also try to collect previous logs.
    This is similar to:
    kubectl logs <pod-name> -n aiops-demo --previous
    """
    pods = v1.list_namespaced_pod(namespace=NAMESPACE)

    logs_data = []

    for pod in pods.items:
        pod_name = pod.metadata.name

        current_logs = ""
        previous_logs = ""
        current_log_error = None
        previous_log_error = None

        try:
            current_logs = v1.read_namespaced_pod_log(
                name=pod_name,
                namespace=NAMESPACE,
                tail_lines=100
            )
        except Exception as e:
            current_log_error = str(e)

        try:
            previous_logs = v1.read_namespaced_pod_log(
                name=pod_name,
                namespace=NAMESPACE,
                previous=True,
                tail_lines=100
            )
        except Exception as e:
            previous_log_error = str(e)

        logs_data.append({
            "pod_name": pod_name,
            "namespace": NAMESPACE,
            "current_logs": current_logs,
            "previous_logs": previous_logs,
            "current_log_error": current_log_error,
            "previous_log_error": previous_log_error,
        })

    return logs_data


def build_incident_snapshot(v1):
    """
    Build one complete incident snapshot.

    One snapshot = current cluster evidence at one point in time.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    snapshot = {
        "snapshot_id": f"incident_snapshot_{timestamp}",
        "timestamp": timestamp,
        "namespace": NAMESPACE,
        "pods": collect_pods(v1),
        "events": collect_events(v1),
        "logs": collect_logs(v1),
    }

    return snapshot


def save_snapshot(snapshot):
    """
    Save snapshot as JSON inside data/raw.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    filename = f"{snapshot['snapshot_id']}.json"
    output_path = os.path.join(OUTPUT_DIR, filename)

    with open(output_path, "w") as f:
        json.dump(snapshot, f, indent=2)

    print(f"Saved incident snapshot: {output_path}")


def main():
    load_kubernetes_config()

    v1 = client.CoreV1Api()

    snapshot = build_incident_snapshot(v1)

    save_snapshot(snapshot)

    print("\nCollection Summary")
    print("------------------")
    print(f"Namespace: {snapshot['namespace']}")
    print(f"Pods collected: {len(snapshot['pods'])}")
    print(f"Events collected: {len(snapshot['events'])}")
    print(f"Logs collected: {len(snapshot['logs'])}")


if __name__ == "__main__":
    main()