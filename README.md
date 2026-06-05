# CIFAR-10 FaaS — Serverless Inference on 5G MEC

## Architecture

```
UE (5G device)
  │  POST /predict  (multipart/form-data, field: "file")
  ▼
gNB → AMF/SMF → UPF  ──── Data Network route → Knative Ingress Gateway IP
                                                        │
                                                        ▼
                                               Knative Service (cifar10-faas)
                                                        │
                                                        ▼
                                               FastAPI + TF/Keras CIFAR-10 CNN
```

## Quick Start

### 1. Build the Docker image

```bash
# EPOCHS=5 for a quick test build (~85% acc needs 20 epochs)
docker build --build-arg EPOCHS=20 -t cifar10-faas:latest .

# Push to your registry
docker tag cifar10-faas:latest <registry>/cifar10-faas:v1.0.0
docker push <registry>/cifar10-faas:v1.0.0
```

### 2. Deploy to Knative

```bash
# Update the image field in knative-service.yaml first, then:
kubectl apply -f knative-service.yaml

# Watch rollout
kubectl get ksvc cifar10-faas -w
```

### 3. Get the Knative Ingress Gateway IP

```bash
kubectl get svc -n knative-serving
# or for Istio ingress:
kubectl get svc istio-ingressgateway -n istio-system
```

Configure this IP as the **Data Network** destination in your UPF (e.g., free5gc UPF config or ULCL rules).

### 4. Test from a UE (or simulate with curl)

```bash
# From a UE in the 5G network (replace with Knative gateway IP/hostname):
curl -X POST http://<knative-ingress-ip>/predict \
     -F "file=@/path/to/image.jpg"

# Example response:
# {
#   "prediction": "cat",
#   "confidence": 0.8732,
#   "top_k": [
#     {"rank": 1, "class": "cat",  "confidence": 0.8732},
#     {"rank": 2, "class": "dog",  "confidence": 0.0821},
#     {"rank": 3, "class": "deer", "confidence": 0.0201}
#   ],
#   "latency_ms": 18.4,
#   "filename": "image.jpg"
# }
```

## API Reference

| Method | Path       | Description                        |
|--------|------------|------------------------------------|
| GET    | `/`        | Service info and class list        |
| GET    | `/health`  | Liveness / readiness probe         |
| POST   | `/predict` | Image classification (multipart)   |

## Scaling Behavior

| Setting | Value | Notes |
|---------|-------|-------|
| `minScale` | `0` | Scale to zero when idle. Set to `1` to avoid cold start in latency tests |
| `maxScale` | `10` | Max pods under burst traffic from UEs |
| `containerConcurrency` | `10` | Concurrent requests per pod before new pod spawns |

## CIFAR-10 Classes

airplane · automobile · bird · cat · deer · dog · frog · horse · ship · truck

## Files

```
faas_app/
├── model/
│   └── train.py              # CNN training script (runs in Docker build stage)
├── app/
│   ├── main.py               # FastAPI app
│   └── cifar10_classes.py    # Class label map
├── Dockerfile                # Multi-stage: train → serve
├── knative-service.yaml      # Knative Service + optional NodePort
└── requirements.txt
```
