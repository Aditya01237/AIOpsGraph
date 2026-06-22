# Linux OOM and Exit Code 137

## Meaning

OOM means Out Of Memory.

In Linux, when memory is exhausted, the kernel may kill a process to protect the system.

In containers, memory is controlled using cgroups. If a container crosses its memory limit, the process inside the container can be killed.

## Exit Code 137

Exit code 137 usually means the process was killed using SIGKILL.

In Kubernetes OOMKilled incidents, exit code 137 is a strong signal that the container crossed its memory limit.

## Important Clues

- Kubernetes last state shows OOMKilled
- Exit code is 137
- Restart count is increasing
- Memory limit is configured too low
- Application allocates too much memory
- Application may have a memory leak

## Container Memory Limit

Kubernetes memory limits are enforced by the container runtime and Linux cgroups.

If the application uses more memory than the configured limit, Kubernetes can mark the container as OOMKilled.

## Fix Suggestions

- Increase memory limit
- Reduce application memory usage
- Profile memory allocation
- Avoid loading large data fully in memory
- Add resource monitoring
- Tune application runtime memory settings