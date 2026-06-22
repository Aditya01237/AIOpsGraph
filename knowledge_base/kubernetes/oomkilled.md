# OOMKilled

## Meaning

OOMKilled means the container exceeded its memory limit and was killed.

OOM means Out Of Memory.

In Kubernetes, this is usually visible in the container last state.

## Common Causes

- Memory limit is too low
- Application memory leak
- Large in-memory data processing
- Bad JVM heap configuration
- Bad runtime memory configuration
- Traffic spike
- Unbounded cache growth
- Unbounded list or object creation

## Important Evidence

- Last state reason is OOMKilled
- Exit code is 137
- Restart count is increasing
- Container memory limit is low
- Events may show the container was killed
- Logs may show memory-heavy operation before crash

## Useful Commands

```bash
kubectl describe pod <pod-name> -n <namespace>
kubectl logs <pod-name> -n <namespace> --previous
kubectl top pod <pod-name> -n <namespace>
kubectl get pod <pod-name> -n <namespace> -o yaml