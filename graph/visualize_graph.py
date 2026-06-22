import os
import json
import argparse
from typing import Dict, List, Any


try:
    from pyvis.network import Network
except ImportError:
    print("pyvis is not installed.")
    print("Install it using: python3 -m pip install pyvis")
    raise


GRAPH_FILE = "data/graph/incident_graph.json"
OUTPUT_DIR = "visualizations"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "incident_graph_clean.html")


NODE_COLORS = {
    "Incident": "#ff6b6b",
    "Namespace": "#74b9ff",
    "Pod": "#55efc4",
    "Container": "#81ecec",
    "EventSummary": "#ffeaa7",
    "LogSummary": "#fab1a0",
    "RootCauseSignal": "#a29bfe",
}


NODE_SHAPES = {
    "Incident": "star",
    "Namespace": "box",
    "Pod": "dot",
    "Container": "ellipse",
    "EventSummary": "triangle",
    "LogSummary": "database",
    "RootCauseSignal": "diamond",
}


def load_graph(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Graph file not found: {path}\n"
            "Run first: python3 graph/graph_builder.py"
        )

    with open(path, "r") as f:
        return json.load(f)


def build_node_map(graph: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    node_map = {}

    for node in graph.get("nodes", []):
        node_map[node.get("id")] = node

    return node_map


def get_nodes_by_type(graph: Dict[str, Any], node_type: str) -> List[Dict[str, Any]]:
    return [
        node for node in graph.get("nodes", [])
        if node.get("type") == node_type
    ]


def get_latest_incident(graph: Dict[str, Any]) -> Dict[str, Any]:
    incidents = get_nodes_by_type(graph, "Incident")

    if not incidents:
        return {}

    incidents.sort(
        key=lambda node: str(node.get("properties", {}).get("timestamp", "")),
        reverse=True
    )

    return incidents[0]


def get_connected_nodes(
    graph: Dict[str, Any],
    source_id: str,
    relation: str
) -> List[Dict[str, Any]]:
    node_map = build_node_map(graph)
    connected = []

    for edge in graph.get("edges", []):
        if edge.get("source") == source_id and edge.get("relation") == relation:
            target_id = edge.get("target")
            target_node = node_map.get(target_id)

            if target_node:
                connected.append(target_node)

    return connected


def get_unique_event_reasons(events: List[Dict[str, Any]]) -> List[str]:
    reasons = []

    for event in events:
        reason = event.get("properties", {}).get("reason")

        if reason and reason not in reasons:
            reasons.append(reason)

    return reasons


def get_log_pods(logs: List[Dict[str, Any]]) -> List[str]:
    pods = []

    for log in logs:
        pod_name = log.get("properties", {}).get("pod_name")

        if pod_name and pod_name not in pods:
            pods.append(pod_name)

    return pods


def short_text(text: Any, max_len: int = 35) -> str:
    if text is None:
        return "unknown"

    text = str(text)

    if len(text) <= max_len:
        return text

    return text[:max_len] + "..."


def make_title(node: Dict[str, Any]) -> str:
    properties = node.get("properties", {})

    return (
        f"ID: {node.get('id')}\n"
        f"Type: {node.get('type')}\n"
        f"Label: {node.get('label')}\n\n"
        f"Properties:\n{json.dumps(properties, indent=2)}"
    )


def add_visual_node(
    net: Network,
    node_id: str,
    label: str,
    node_type: str,
    title: str,
    level: int
) -> None:
    color = NODE_COLORS.get(node_type, "#dfe6e9")
    shape = NODE_SHAPES.get(node_type, "dot")

    net.add_node(
        node_id,
        label=short_text(label),
        title=title,
        color=color,
        shape=shape,
        level=level
    )


def add_visual_edge(
    net: Network,
    source: str,
    target: str,
    relation: str
) -> None:
    net.add_edge(
        source,
        target,
        label=relation,
        title=relation,
        arrows="to"
    )


def build_clean_visual_graph(graph: Dict[str, Any]) -> Dict[str, Any]:
    incident = get_latest_incident(graph)

    if not incident:
        return {
            "nodes": [],
            "edges": []
        }

    incident_id = incident.get("id")

    namespaces = get_connected_nodes(graph, incident_id, "OCCURRED_IN")
    root_causes = get_connected_nodes(graph, incident_id, "HAS_ROOT_CAUSE_SIGNAL")
    pods = get_connected_nodes(graph, incident_id, "AFFECTS")
    events = get_connected_nodes(graph, incident_id, "HAS_EVENT")
    logs = get_connected_nodes(graph, incident_id, "HAS_LOG")

    clean_nodes = []
    clean_edges = []

    clean_nodes.append(incident)

    for namespace in namespaces:
        clean_nodes.append(namespace)
        clean_edges.append({
            "source": incident_id,
            "target": namespace.get("id"),
            "relation": "OCCURRED_IN"
        })

    for root_cause in root_causes:
        clean_nodes.append(root_cause)
        clean_edges.append({
            "source": incident_id,
            "target": root_cause.get("id"),
            "relation": "HAS_ROOT_CAUSE"
        })

    for pod in pods:
        pod_id = pod.get("id")
        clean_nodes.append(pod)

        clean_edges.append({
            "source": incident_id,
            "target": pod_id,
            "relation": "AFFECTS"
        })

        containers = get_connected_nodes(graph, pod_id, "HAS_CONTAINER")

        for container in containers:
            clean_nodes.append(container)
            clean_edges.append({
                "source": pod_id,
                "target": container.get("id"),
                "relation": "HAS_CONTAINER"
            })

    event_reasons = get_unique_event_reasons(events)
    event_summary_id = f"event_summary:{incident_id}"

    event_summary_node = {
        "id": event_summary_id,
        "type": "EventSummary",
        "label": f"Events: {len(events)}",
        "properties": {
            "event_count": len(events),
            "unique_reasons": event_reasons[:10]
        }
    }

    clean_nodes.append(event_summary_node)
    clean_edges.append({
        "source": incident_id,
        "target": event_summary_id,
        "relation": "HAS_EVENTS"
    })

    log_pods = get_log_pods(logs)
    log_summary_id = f"log_summary:{incident_id}"

    log_summary_node = {
        "id": log_summary_id,
        "type": "LogSummary",
        "label": f"Logs: {len(logs)}",
        "properties": {
            "log_count": len(logs),
            "pods_with_logs": log_pods[:10]
        }
    }

    clean_nodes.append(log_summary_node)
    clean_edges.append({
        "source": incident_id,
        "target": log_summary_id,
        "relation": "HAS_LOGS"
    })

    unique_nodes = {}
    for node in clean_nodes:
        unique_nodes[node.get("id")] = node

    unique_edges = []
    seen_edges = set()

    for edge in clean_edges:
        key = (
            edge.get("source"),
            edge.get("target"),
            edge.get("relation")
        )

        if key not in seen_edges:
            unique_edges.append(edge)
            seen_edges.add(key)

    return {
        "nodes": list(unique_nodes.values()),
        "edges": unique_edges
    }


def get_node_level(node_type: str) -> int:
    levels = {
        "Incident": 1,
        "Namespace": 2,
        "RootCauseSignal": 2,
        "Pod": 2,
        "EventSummary": 2,
        "LogSummary": 2,
        "Container": 3,
    }

    return levels.get(node_type, 3)


def create_visualization(clean_graph: Dict[str, Any], output_file: str) -> None:
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    net = Network(
        height="850px",
        width="100%",
        directed=True,
        bgcolor="#ffffff",
        font_color="#222222"
    )

    for node in clean_graph.get("nodes", []):
        node_type = node.get("type", "Unknown")

        add_visual_node(
            net=net,
            node_id=node.get("id"),
            label=node.get("label"),
            node_type=node_type,
            title=make_title(node),
            level=get_node_level(node_type)
        )

    for edge in clean_graph.get("edges", []):
        add_visual_edge(
            net=net,
            source=edge.get("source"),
            target=edge.get("target"),
            relation=edge.get("relation")
        )

    net.set_options("""
    {
      "layout": {
        "hierarchical": {
          "enabled": true,
          "direction": "LR",
          "sortMethod": "directed",
          "levelSeparation": 260,
          "nodeSpacing": 180,
          "treeSpacing": 220
        }
      },
      "physics": {
        "enabled": false
      },
      "nodes": {
        "borderWidth": 2,
        "font": {
          "size": 18
        }
      },
      "edges": {
        "font": {
          "size": 12,
          "align": "middle"
        },
        "color": {
          "color": "#636e72"
        },
        "smooth": {
          "enabled": true,
          "type": "cubicBezier"
        }
      },
      "interaction": {
        "hover": true,
        "navigationButtons": true,
        "keyboard": true,
        "zoomView": true,
        "dragView": true
      }
    }
    """)

    net.write_html(output_file, open_browser=False)

    print(f"Saved clean graph visualization: {output_file}")


def print_summary(clean_graph: Dict[str, Any]) -> None:
    nodes = clean_graph.get("nodes", [])
    edges = clean_graph.get("edges", [])

    print("\nClean Graph Summary")
    print("-------------------")
    print(f"Nodes shown: {len(nodes)}")
    print(f"Edges shown: {len(edges)}")

    type_count = {}

    for node in nodes:
        node_type = node.get("type", "Unknown")
        type_count[node_type] = type_count.get(node_type, 0) + 1

    print("\nNode Types")
    print("----------")

    for node_type, count in sorted(type_count.items()):
        print(f"{node_type}: {count}")


def main():
    parser = argparse.ArgumentParser(
        description="Create clean AIOpsGraph visualization"
    )

    parser.add_argument(
        "--input",
        type=str,
        default=GRAPH_FILE,
        help="Input incident graph JSON"
    )

    parser.add_argument(
        "--output",
        type=str,
        default=OUTPUT_FILE,
        help="Output HTML visualization"
    )

    args = parser.parse_args()

    graph = load_graph(args.input)
    clean_graph = build_clean_visual_graph(graph)

    if not clean_graph.get("nodes"):
        print("No incident found in graph.")
        return

    print_summary(clean_graph)
    create_visualization(clean_graph, args.output)

    print("\nOpen using:")
    print(f"open {args.output}")


if __name__ == "__main__":
    main()