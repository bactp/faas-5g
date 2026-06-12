# image-classifier

## Description
Image classifier FaaS application using Knative serving with scale-to-zero.

## Usage

### Fetch the package
`kpt pkg get REPO_URI[.git]/workloads/general/image-classifier[@VERSION] image-classifier`

### View package content
`kpt pkg tree image-classifier`

### Apply the package
```
kpt live init image-classifier
kpt live apply image-classifier --reconcile-timeout=2m --output=table
```
