import json
import os
import argparse
from typing import Dict, List, Any

GRAPH_FILE = "data/graph/incident_graph.json"

def load_graph(path:str = GRAPH_FILE) -> Dict[str,Any]:
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Graph file not found: {path}\n"
            "Run: python graph/graph_builder.py"
        )
    
    with open(path,"r") as f:
        return json.load(f)
    
def get_nodes_by_type(graph:Dict[str,Any], node_type:str) -> List[Dict[str,Any]]:
    return [
        node for node in graph.get("nodes",[])
        if node.get("type") == node_type
    ]

def get_node_by_id(graph:Dict[str,Any], node_id:str) -> Dict[str,Any]:
    for node in graph.get("nodes",[]):
        if node.get("id") == node_id:
            return node
    return {}

def get_edges_from(graph:Dict[str,Any], source_id:str, relation:str = None) -> List[Dict[str,Any]]:
    edges = []
    
    for edge in graph.get("edges",[]):
        if edge.get("source") != source_id:
            continue
        if relation and edge.get("relation") != relation:
            continue
        edges.append(edge)
    return edges

def get_connected_nodes(graph:Dict[str,Any], source_id:str, relation: str = None) -> List[Dict[str,Any]]:
    connected = []

    edges = get_edges_from(graph,source_id,relation)
    for edge in edges:
        target_id = edge.get("target")
        node = get_node_by_id(graph,target_id)
        if node:
            connected.append(node)

    return connected

def list_incidents(graph: Dict[str,Any]) -> None:
    incidents = get_nodes_by_type(graph,"Incident")

    if not incidents:
        print("No incident graph found in graph.")
        return
    
    print("\nIncidents")
    print("----------")

    for index, incident in enumerate(incidents, start=1):
        print(f"{index}. {incident['id']}")
        print(f"    Type:{incident.get('label')}")
        print(f"    Timestamp: {incident.get('properties',{}).get('timestamp')}")
        print()


def show_root_cause(graph: Dict[str, Any], incident_id: str) -> None:
    root_causes = get_connected_nodes(graph, incident_id, "HAS_ROOT_CAUSE_SIGNAL")

    print("\nRoot Cause Signal")
    print("-----------------")

    if not root_causes:
        print("No root cause signal found.")
        return

    for root in root_causes:
        print(f"Type: {root.get('label')}")
        print(f"Signal: {root.get('properties', {}).get('signal')}")

def show_affected_pods(graph: Dict[str, Any], incident_id: str) -> None:
    pods = get_connected_nodes(graph, incident_id, "AFFECTS")

    print("\nAffected Pods")
    print("-------------")

    if not pods:
        print("No affected pods found.")
        return

    for pod in pods:
        props = pod.get("properties", {})
        print(f"Pod: {pod.get('label')}")
        print(f"  App: {props.get('app')}")
        print(f"  Phase: {props.get('phase')}")
        print(f"  Ready: {props.get('ready')}")
        print(f"  Restart Count: {props.get('restart_count')}")
        print(f"  State: {props.get('state')}")
        print(f"  Last State: {props.get('last_state')}")
        print()

def show_events(graph: Dict[str, Any], incident_id: str) -> None:
    events = get_connected_nodes(graph, incident_id, "HAS_EVENT")

    print("\nImportant Events")
    print("----------------")

    if not events:
        print("No important events found.")
        return

    for event in events:
        props = event.get("properties", {})
        print(f"Reason: {props.get('reason')}")
        print(f"Type: {props.get('type')}")
        print(f"Object: {props.get('object_name')}")
        print(f"Message: {props.get('message')}")
        print()

def show_logs(graph: Dict[str, Any], incident_id: str) -> None:
    logs = get_connected_nodes(graph, incident_id, "HAS_LOG")

    print("\nImportant Logs")
    print("--------------")

    if not logs:
        print("No important logs found.")
        return

    for log in logs:
        props = log.get("properties", {})
        print(f"Pod: {props.get('pod_name')}")
        print("Log Excerpt:")
        print(props.get("log_excerpt"))
        print()

def show_incident_context(graph: Dict[str, Any], incident_id: str) -> None:
    incident = get_node_by_id(graph, incident_id)

    if not incident:
        print(f"Incident not found: {incident_id}")
        return

    print("\nIncident Context")
    print("================")
    print(f"Incident ID: {incident.get('id')}")
    print(f"Incident Type: {incident.get('label')}")
    print(f"Timestamp: {incident.get('properties', {}).get('timestamp')}")

    show_root_cause(graph, incident_id)
    show_affected_pods(graph, incident_id)
    show_events(graph, incident_id)
    show_logs(graph, incident_id)

def get_first_incident_id(graph: Dict[str, Any]) -> str:
    incidents = get_nodes_by_type(graph, "Incident")

    if not incidents:
        return ""

    return incidents[0].get("id")

def main():
    parser = argparse.ArgumentParser(description="Query AIOpsGraph incident graph")

    parser.add_argument(
        "--list-incidents",
        action="store_true",
        help="List all incidents in the graph"
    )

    parser.add_argument(
        "--incident-id",
        type=str,
        help="Incident node id"
    )

    parser.add_argument(
        "--root-cause",
        action="store_true",
        help="Show root cause signal for incident"
    )

    parser.add_argument(
        "--pods",
        action="store_true",
        help="Show affected pods for incident"
    )

    parser.add_argument(
        "--events",
        action="store_true",
        help="Show events for incident"
    )

    parser.add_argument(
        "--logs",
        action="store_true",
        help="Show logs for incident"
    )

    parser.add_argument(
        "--context",
        action="store_true",
        help="Show full incident context"
    )

    args = parser.parse_args()

    graph = load_graph()

    if args.list_incidents:
        list_incidents(graph)
        return

    incident_id = args.incident_id or get_first_incident_id(graph)

    if not incident_id:
        print("No incident found in graph.")
        return

    if args.root_cause:
        show_root_cause(graph, incident_id)
    elif args.pods:
        show_affected_pods(graph, incident_id)
    elif args.events:
        show_events(graph, incident_id)
    elif args.logs:
        show_logs(graph, incident_id)
    elif args.context:
        show_incident_context(graph, incident_id)
    else:
        show_incident_context(graph, incident_id)


if __name__ == "__main__":
    main()