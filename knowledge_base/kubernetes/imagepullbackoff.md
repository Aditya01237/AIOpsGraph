# ImagePullBackOff

## Meaning

ImagePullBackOff means Kubernetes cannot pull the container image.

In this case, the container usually does not start, so application logs may not be available.

## Common Causes

- Wrong image name
- Wrong image tag
- Image does not exist
- Private image without imagePullSecret
- Registry authentication failure
- Registry connectivity issue
- DNS issue
- Rate limit from image registry

## Important Evidence

- Pod status shows ErrImagePull
- Pod status shows ImagePullBackOff
- Container state is Waiting
- Events show Failed to pull image
- Events show Back-off pulling image
- Application logs are usually unavailable because the container never started

## Useful Commands

```bash
kubectl get pods -n <namespace>
kubectl describe pod <pod-name> -n <namespace>
kubectl get events -n <namespace> --sort-by=.lastTimestamp
docker pull <image-name>
kubectl get secret -n <namespace>