# Day 4: Kubernetes Incident Collector

## Goal

Build a Python collector that automatically captures Kubernetes incident evidence.

Instead of manually running:

```bash
kubectl get pods
kubectl describe pod
kubectl logs
kubectl get events
```

we collect the same signals using the Kubernetes Python client and store them as JSON.

---

## File Created

```txt
collector/k8s_collector.py
```

---

## What the Collector Captures

The collector captures three main things:

```txt
1. Pod and container status
2. Kubernetes events
3. Pod logs
```

---

## 1. Pod and Container Status

Collected fields:

```txt
pod_name
namespace
labels
node_name
pod phase
pod IP
container image
container readiness
restart count
current state
last state
```

This helps detect signals like:

```txt
CrashLoopBackOff
restart_count > 0
container not ready
last_state = terminated
exit_code = 1
```

---

## 2. Kubernetes Events

Events explain what Kubernetes is doing.

Examples:

```txt
Scheduled
Pulled
Started
BackOff
ErrImagePull
FailedScheduling
OOMKilled
```

For CrashLoopBackOff, the important event is:

```txt
Back-off restarting failed container
```

---

## 3. Pod Logs

The collector stores:

```txt
current_logs
previous_logs
```

Previous logs are important for CrashLoopBackOff because the container may have already restarted.

Equivalent command:

```bash
kubectl logs <pod-name> -n aiops-demo --previous
```

---

## Output

Raw snapshots are saved in:

```txt
data/raw/
```

Example:

```txt
data/raw/incident_snapshot_20260601_153000.json
```

Each snapshot contains:

```json
{
  "snapshot_id": "incident_snapshot_20260601_153000",
  "timestamp": "20260601_153000",
  "namespace": "aiops-demo",
  "pods": [],
  "events": [],
  "logs": []
}
```

---

## Run Collector

From project root:

```bash
python collector/k8s_collector.py
```

Expected output:

```txt
Loaded local kubeconfig
Saved incident snapshot: data/raw/incident_snapshot_xxxxx.json

Collection Summary
------------------
Namespace: aiops-demo
Pods collected: 2
Events collected: 10
Logs collected: 2
```

---

## Verify CrashLoopBackOff Evidence

```bash
grep -i "crashloopbackoff" data/raw/*.json
grep -i "back-off" data/raw/*.json
grep -i "exit_code" data/raw/*.json
grep -i "simulating application startup failure" data/raw/*.json
```

Expected evidence:

```txt
state contains CrashLoopBackOff
event contains Back-off restarting failed container
last_state contains exit_code 1
logs contain simulated startup failure
```

---

## Why This Matters

Manual debugging is useful for humans, but AIOps needs structured data.

This collector converts Kubernetes signals into JSON so that later we can build:

```txt
Raw Snapshot
↓
Processed Incident Summary
↓
Kubernetes Graph
↓
RAG-based RCA
```

---

## Interview Explanation

You can say:

> I built a Kubernetes collector using the official Python client. It collects pod status, container state, restart count, Kubernetes events, and current/previous logs from the namespace. The collector stores this evidence as timestamped JSON snapshots, which become the raw input for the RCA pipeline.

---

## Key Interview Points

### Why Kubernetes Python client?

Because shell commands are good for manual debugging, but an AIOps system needs structured programmable data.

### Why collect previous logs?

Because in CrashLoopBackOff, the latest container may not contain the crash output. Previous logs often show the actual failure.

### Why collect events?

Logs explain application behavior. Events explain Kubernetes behavior.

### Why raw JSON?

Raw JSON preserves original evidence before preprocessing.

---

## Git Commit

```bash
git status
git add .
git commit -m "Add Kubernetes incident collector"
```