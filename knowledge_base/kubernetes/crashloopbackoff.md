# CrashLoopBackOff

## Meaning

CrashLoopBackOff means a container starts, crashes, restarts, and then Kubernetes waits before restarting it again.

It is not the final root cause. It is a symptom that the application or container process is failing again and again.

## Common Causes

- Application startup error
- Wrong container command or arguments
- Missing environment variable
- Missing ConfigMap
- Missing Secret
- Application dependency is unavailable
- Permission issue
- Port binding issue
- Bad application configuration

## Important Evidence

- Pod status shows CrashLoopBackOff
- Restart count keeps increasing
- Container state is Waiting
- Last state is Terminated
- Exit code is non-zero
- Events show Back-off restarting failed container
- Previous logs show the actual crash reason

## Useful Commands

```bash
kubectl get pods -n <namespace>
kubectl describe pod <pod-name> -n <namespace>
kubectl logs <pod-name> -n <namespace>
kubectl logs <pod-name> -n <namespace> --previous
kubectl get events -n <namespace> --sort-by=.lastTimestamp