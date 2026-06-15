# knative-config

## Description
Site-specific Knative configuration. Applied after knative-serving and kourier.
**Must be edited per cluster before approving the PackageRevision.**

## Per-cluster values to edit

| File | Field | Value |
|------|-------|-------|
| `config-domain.yaml` | data key | `<CLUSTER_MASTER_IP>.sslip.io` |

## Cluster master IPs
- 5g-core:     192.168.28.113
- 5g-edge:     192.168.28.188
- 5g-regional: 192.168.28.128
- standby:     192.168.28.154

## Usage

### Fetch the package
`kpt pkg get REPO_URI[.git]/serverless-platform/knative-config[@VERSION] knative-config`

### View package content
`kpt pkg tree knative-config`

### Apply the package
```
kpt live init knative-config --namespace knative-serving --name inventory-knative-config
kpt live apply knative-config --reconcile-timeout=2m --output=table
```
