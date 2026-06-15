# kourier

## Description
Kourier Ingress Gateway for Knative Serving v1.15.0. Configures Kourier as the default
ingress class for Knative. Requires knative-serving to be deployed first.

## Usage

### Fetch the package
`kpt pkg get REPO_URI[.git]/serverless-platform/kourier[@VERSION] kourier`

### View package content
`kpt pkg tree kourier`

### Apply the package
```
kpt live init kourier --namespace kourier-system --name inventory-kourier
kpt live apply kourier --reconcile-timeout=2m --output=table
```
