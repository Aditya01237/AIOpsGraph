# Kubernetes Debugging Commands

## Pod Status

```bash
kubectl get pods -n <namespace>
```

Shows pod readiness, status, restarts, and age.

Use this first to quickly identify unhealthy pods.

## Pod Details

```bash
kubectl describe pod <pod-name> -n <namespace>
```

Shows detailed information about the pod.

This includes:

- Container state
- Last state
- Exit code
- Restart count
- Events
- Image pull errors
- Node name
- Resource requests and limits

## Current Logs

```bash
kubectl logs <pod-name> -n <namespace>
```

Shows logs from the current running container.

## Previous Logs

```bash
kubectl logs <pod-name> -n <namespace> --previous
```

Shows logs from the previous crashed container.

This is very useful for:

- CrashLoopBackOff
- OOMKilled
- Containers that restart quickly

## Events

```bash
kubectl get events -n <namespace> --sort-by=.lastTimestamp
```

Shows Kubernetes-side events.

Useful reasons include:

- BackOff
- Failed
- ErrImagePull
- ImagePullBackOff
- FailedScheduling
- Killing

## Resource Usage

```bash
kubectl top pod -n <namespace>
kubectl top node
```

Shows CPU and memory usage.

This requires metrics-server to be installed.

## YAML Output

```bash
kubectl get pod <pod-name> -n <namespace> -o yaml
```

Shows the complete pod YAML, including status, spec, resource limits, and container details.