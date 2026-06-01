# AIOpsGraph

AIOpsGraph is a Graph-RAG based Root Cause Analysis system for Kubernetes incidents.

## Problem

Kubernetes incidents such as CrashLoopBackOff, ImagePullBackOff, and OOMKilled generate logs, events, pod status changes, and metrics across multiple resources. Traditional debugging requires manually checking many commands like:

```bash
kubectl get pods
kubectl describe pod
kubectl logs
kubectl get events