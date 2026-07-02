# FaaS-5G: Function-as-a-Service over 5G Network with Nephio

A project demonstrating the integration of **Function-as-a-Service (FaaS)** with a **5G standalone core network**, deployed and managed through the [Nephio](https://nephio.org/) cloud-native network automation platform on AWS infrastructure.

The system runs a **free5gc** 5G core across dedicated workload clusters, establishes an end-to-end PDU session from a simulated UE, and routes traffic to a **Knative**-hosted serverless image classification service — validating FaaS autoscaling behaviour driven by real 5G data-plane traffic.

---

## System Architecture

![System Architecture](docs/images/faas_5g/faas5g_architecture.png)

---

## Deployment Phases

### Phase 1 — Infrastructure: Cluster Provisioning on AWS

Bootstrap a Nephio management cluster on AWS EC2 and use it to provision two Cluster API workload clusters (core, edge) automatically.

**Covers:** Management cluster bootstrap · AWS credential setup (STS/MFA) · CAPA workload cluster creation · kubeconfig retrieval

→ [01-clusters-setup.md](docs/01-clusters-setup.md)

---

### Phase 2 — Network Preparation: 5G Interface Setup

Prepare the AWS network infrastructure and worker nodes for the 5G data plane — creating dedicated subnets, Elastic Network Interfaces (ENIs), and attaching them to the workload cluster nodes. 

**Covers:** gtp5g kernel module installation · 5G subnet & ENI creation on AWS Console · ENI attachment to core/edge worker nodes · Interface bring-up and mapping.

→ [02-5g-stack-setup.md](docs/02-5g-stack-setup.md)

---

### Phase 3 — Stack Deployment & FaaS Demo

Deploy the complete free5gc 5G stack and the Knative serverless platform using the Nephio package-based approach, then run an end-to-end demonstration of FaaS traffic flowing through the 5G data path.

**Phase 3a — 5G Core (free5gc):**
- Register the workload catalog repository with Nephio
- Deploy Control Plane NFs (AMF, SMF, NRF, UDM, ...) on the core cluster
- Provision UE subscriber credentials via the free5gc WebUI
- Deploy UPF and UERANSIM (gNB + UE) on the edge cluster
- Verify PDU session establishment and `uesimtun0` tunnel interface

**Phase 3b — FaaS Platform (Knative + Image Classifier):**
- Deploy Knative core onto the edge cluster (Kourier ingress auto-configured)
- Deploy the serverless image-classification application
- Configure UPF NAT routing and UE tunnel route for application traffic
- Demonstrate scale-from-zero on first request over the 5G data path
- Load test with multiple concurrent requests to trigger autoscaling

→ [03-faas-5g-stack-setup.md](docs/03-faas-5g-stack-setup.md)

---