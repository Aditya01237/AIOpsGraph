import os
import sys
import glob
import argparse
import subprocess
from typing import List


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

RAW_DIR = "data/raw"
PROCESSED_DIR = "data/processed"
GRAPH_FILE = "data/graph/incident_graph.json"
FINAL_RCA_JSON = "data/rca/final_rca_report.json"
FINAL_RCA_MD = "data/reports/final_rca_report.md"


def run_command(command: List[str], description: str) -> bool:
    """
    Run one command and print clean status.
    """
    print("\n" + "=" * 70)
    print(description)
    print("=" * 70)
    print("Command:", " ".join(command))
    print()

    result = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True
    )

    if result.stdout:
        print(result.stdout)

    if result.stderr:
        print(result.stderr)

    if result.returncode != 0:
        print(f"FAILED: {description}")
        return False

    print(f"SUCCESS: {description}")
    return True


def count_json_files(folder: str) -> int:
    """
    Count JSON files inside a folder.
    """
    path = os.path.join(PROJECT_ROOT, folder, "*.json")
    return len(glob.glob(path))


def check_file_exists(path: str) -> bool:
    """
    Check if a file exists from project root.
    """
    return os.path.exists(os.path.join(PROJECT_ROOT, path))


def print_project_header() -> None:
    print("\nAIOpsGraph Demo Runner")
    print("======================")
    print("This script runs the complete RCA pipeline.")
    print()
    print("Pipeline:")
    print("Kubernetes evidence")
    print("  -> raw snapshot")
    print("  -> processed incident")
    print("  -> incident graph")
    print("  -> RCA rules")
    print("  -> retrieved knowledge")
    print("  -> Markdown report")


def validate_inputs(skip_collect: bool) -> bool:
    """
    Validate that required input data exists.
    """
    raw_count = count_json_files(RAW_DIR)
    processed_count = count_json_files(PROCESSED_DIR)

    print("\nInput Check")
    print("-----------")
    print(f"Raw snapshots found: {raw_count}")
    print(f"Processed incidents found: {processed_count}")

    if skip_collect and raw_count == 0 and processed_count == 0:
        print()
        print("No raw or processed data found.")
        print("Run one of these:")
        print("1. python scripts/run_demo.py --collect")
        print("2. python collector/k8s_collector.py")
        print("   python collector/process_incident.py")
        return False

    return True


def run_pipeline(collect: bool) -> bool:
    """
    Run full AIOpsGraph demo pipeline.
    """

    python = sys.executable

    if collect:
        ok = run_command(
            [python, "collector/k8s_collector.py"],
            "Step 1: Collect Kubernetes raw evidence"
        )
        if not ok:
            return False
    else:
        print("\nSkipping Kubernetes collection.")
        print("Using existing data from data/raw or data/processed.")

    ok = run_command(
        [python, "collector/process_incident.py"],
        "Step 2: Process raw incident snapshots"
    )
    if not ok:
        return False

    ok = run_command(
        [python, "graph/graph_builder.py"],
        "Step 3: Build incident graph"
    )
    if not ok:
        return False

    ok = run_command(
        [python, "graph/graph_query.py", "--context"],
        "Step 4: Query incident graph context"
    )
    if not ok:
        return False

    ok = run_command(
        [python, "rca_engine/run_rca.py", "--save"],
        "Step 5: Run RCA engine with retrieved knowledge"
    )
    if not ok:
        return False

    ok = run_command(
        [python, "rca_engine/report_writer.py"],
        "Step 6: Generate Markdown RCA report"
    )
    if not ok:
        return False

    return True


def print_final_outputs() -> None:
    """
    Print final generated output paths.
    """
    print("\n" + "=" * 70)
    print("Final Demo Output")
    print("=" * 70)

    outputs = [
        GRAPH_FILE,
        FINAL_RCA_JSON,
        FINAL_RCA_MD
    ]

    for output in outputs:
        if check_file_exists(output):
            print(f"Created: {output}")
        else:
            print(f"Missing:  {output}")

    print()
    print("Open Markdown report:")
    print(f"code {FINAL_RCA_MD}")


def main():
    parser = argparse.ArgumentParser(
        description="Run complete AIOpsGraph RCA demo pipeline"
    )

    parser.add_argument(
        "--collect",
        action="store_true",
        help="Collect fresh data from Kubernetes before running RCA"
    )

    args = parser.parse_args()

    print_project_header()

    skip_collect = not args.collect

    if not validate_inputs(skip_collect):
        return

    success = run_pipeline(collect=args.collect)

    if not success:
        print("\nDemo failed. Check the error above.")
        return

    print_final_outputs()

    print("\nDemo completed successfully.")


if __name__ == "__main__":
    main()