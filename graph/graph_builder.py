import json
import os
import glob
from typing import Dict, List, Any

PROCESSED_DIR = "data/processed"
GRAPH_DIR = "data/graph"
GRAPH_OUTPUT_FILE = os.path.join(GRAPH_DIR ,"incident_graph.json")

def load_json(path:str) -> Dict[str,Any]:
    with open(path,"r") as f:
        return json.load(f);

def make_node(node_id:str, node_type:str, label:str, properties: Dict[str,any]) -> Dict[str,any]:
    return {
        "id":node_id,
        "type":node_type,
        "label":label,
        "properties":properties
    }

def make_edge(source:str, target:str, relation:str) -> Dict[str,str]:
    return {
        "source":source,
        "target":target,
        "relation":relation,
    }

def add_node(nodes:Dict[str,Dict[str,Any]], node:Dict[str,any]) -> None:
    nodes[node["id"]] = node

def add_edge(edges:List[Dict[str,str]], edge:Dict[str,str]) -> None:
    if edge not in edges:
        edges.append(edge)

def safe_id(value:str) -> str:
    if value is None:
        return "unknown"
    return (
        str(value)
        .replace(" ","_")
        .replace("/","_")
        .replace(":","_")
        .replace("\n","_")
    )

def build_graph_from_incident(incident:Dict[str,Any], nodes:Dict[str,Dict[str,Any]], edges:List[Dict[str,str]]) -> None:
    snapshot_id = incident.get("snapshot_id","unknown_snapshot")
    namespace = incident.get("namespace","unknown_namespace")
    incident_type = incident.get("incident_type","Unknown")
    root_cause_signal = incident.get("root_cause_signal","Unknown root cause")

    incident_id = f"incident:{safe_id(snapshot_id)}"
    namespace_id = f"namespace:{safe_id(namespace)}"
    root_cause_id = f"root_cause:{safe_id(incident_type)}"

    add_node(
        nodes,
        make_node(
            incident_id,
            "Incident",
            incident_type,
            {
                "snapshot_id": snapshot_id,
                "timestamp": incident.get("timestamp"),
                "source_file": incident.get("source_file")
            }
        )
    )

    add_node(
        nodes,
        make_node(
            namespace_id,
            "Namespace",
            namespace,
            {
                "name": namespace
            }
        )
    )

    add_node(
        nodes,
        make_node(
            root_cause_id,
            "RootCauseSignal",
            incident_type,
            {
                "signal": root_cause_signal
            }
        )
    )

    add_edge(edges, make_edge(incident_id, namespace_id, "OCCURRED_IN"))
    add_edge(edges, make_edge(incident_id, root_cause_id, "HAS_ROOT_CAUSE_SIGNAL"))

    for pod in incident.get("affected_pods", []):
        pod_name = pod.get("pod_name", "unknown_pod")
        container_name = pod.get("container_name", "unknown_container")

        pod_id = f"pod:{safe_id(pod_name)}"
        container_id = f"container:{safe_id(pod_name)}:{safe_id(container_name)}"

        add_node(
            nodes,
            make_node(
                pod_id,
                "Pod",
                pod_name,
                {
                    "app": pod.get("app"),
                    "incident_label": pod.get("incident_label"),
                    "phase": pod.get("phase"),
                    "ready": pod.get("ready"),
                    "restart_count": pod.get("restart_count"),
                    "state": pod.get("state"),
                    "last_state": pod.get("last_state")
                }
            )
        )

        add_node(
            nodes,
            make_node(
                container_id,
                "Container",
                container_name,
                {
                    "image": pod.get("image"),
                    "ready": pod.get("ready"),
                    "restart_count": pod.get("restart_count"),
                    "state": pod.get("state"),
                    "last_state": pod.get("last_state")
                }
            )
        )

        add_edge(edges, make_edge(incident_id, pod_id, "AFFECTS"))
        add_edge(edges, make_edge(pod_id, container_id, "HAS_CONTAINER"))

    for index, event in enumerate(incident.get("important_events", [])):
        object_name = event.get("object_name", "unknown_object")
        event_id = f"event:{safe_id(snapshot_id)}:{index}"

        add_node(
            nodes,
            make_node(
                event_id,
                "Event",
                event.get("reason", "UnknownEvent"),
                {
                    "type": event.get("type"),
                    "reason": event.get("reason"),
                    "message": event.get("message"),
                    "object_kind": event.get("object_kind"),
                    "object_name": object_name,
                    "count": event.get("count"),
                    "last_timestamp": event.get("last_timestamp")
                }
            )
        )
        add_edge(edges, make_edge(incident_id, event_id, "HAS_EVENT"))

        if object_name:
            pod_id = f"pod:{safe_id(object_name)}"
            if pod_id in nodes:
                add_edge(edges, make_edge(pod_id, event_id, "EMITS_EVENT"))
    
    for index, log in enumerate(incident.get("important_logs", [])):
        pod_name = log.get("pod_name", "unknown_pod")
        log_id = f"log:{safe_id(snapshot_id)}:{index}"

        add_node(
            nodes,
            make_node(
                log_id,
                "Log",
                f"log-{index}",
                {
                    "pod_name": pod_name,
                    "log_excerpt": log.get("log_excerpt")
                }
            )
        )
        add_edge(edges, make_edge(incident_id, log_id, "HAS_LOG"))

        pod_id = f"pod:{safe_id(pod_name)}"
        if pod_id in nodes:
            add_edge(edges, make_edge(pod_id, log_id, "HAS_LOG"))

def build_graph() -> Dict[str, Any]:
    processed_files = glob.glob(os.path.join(PROCESSED_DIR, "*.json"))
    if not processed_files:
        print("No processed incident files found.")
        print("Run: python collector/process_incident.py")
        return {
            "nodes": [],
            "edges": []
        }
    nodes = {}
    edges = []
    for path in processed_files:
        incident = load_json(path)
        build_graph_from_incident(incident, nodes, edges)
        
    graph = {
        "nodes": list(nodes.values()),
        "edges": edges,
        "metadata": {
            "processed_files_count": len(processed_files),
            "nodes_count": len(nodes),
            "edges_count": len(edges)
        }
    }
    return graph
    
def save_graph(graph: Dict[str, Any]) -> None:
    os.makedirs(GRAPH_DIR, exist_ok=True)

    with open(GRAPH_OUTPUT_FILE, "w") as f:
        json.dump(graph, f, indent=2)

    print(f"Saved graph: {GRAPH_OUTPUT_FILE}")
    print(f"Nodes: {graph['metadata']['nodes_count']}")
    print(f"Edges: {graph['metadata']['edges_count']}")

def main():
    graph = build_graph()
    save_graph(graph)

if __name__ == "__main__":
    main()