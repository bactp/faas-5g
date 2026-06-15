# knative-serving

## Description
Knative Serving Core components v1.15.0. Requires knative-crds to be deployed first.

## Usage

### Fetch the package
`kpt pkg get REPO_URI[.git]/serverless-platform/knative-serving[@VERSION] knative-serving`

### View package content
`kpt pkg tree knative-serving`

### Apply the package
```
kpt live init knative-serving --namespace knative-serving --name inventory-knative-serving
kpt live apply knative-serving --reconcile-timeout=5m --output=table
```
