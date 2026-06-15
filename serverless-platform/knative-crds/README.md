# knative-crds

## Description
Knative Serving CRDs v1.15.0. Must be deployed before knative-serving.

## Usage

### Fetch the package
`kpt pkg get REPO_URI[.git]/serverless-platform/knative-crds[@VERSION] knative-crds`

### View package content
`kpt pkg tree knative-crds`

### Apply the package
```
kpt live init knative-crds --namespace default --name inventory-knative-crds
kpt live apply knative-crds --reconcile-timeout=2m --output=table
```
