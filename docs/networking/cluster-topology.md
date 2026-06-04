---
sidebar_position: 4
title: "Cluster Network Topology"
description: "How packets actually flow inside the cluster — CNI, Istio Ambient HBONE, MetalLB ingress, kube-proxy, and the MetalLB VIP hairpin"
---

# Cluster Network Topology

The [Network Overview](./overview.md) doc covers the L1/L2/L3 view from the UDR down to nodes. This doc covers the **L4/L7 view inside the cluster** — packet flow for the four most-common paths.

## High-level inside-the-cluster

```mermaid
graph TB
    subgraph cluster ["Kubernetes Cluster"]
        subgraph cni ["Calico CNI"]
            podA["Pod A\n192.168.196.x"]
            podB["Pod B\n192.168.248.x"]
        end

        subgraph ambient ["Istio Ambient Mesh (default, loki, argo-workflows, ...)"]
            zt1["ztunnel\nDaemonSet"]
            podC["Pod C (meshed)\n192.168.x.y"]
            podD["Pod D (meshed)\n192.168.x.z"]
        end

        kube_proxy["kube-proxy\n(iptables NAT)"]
        coredns["CoreDNS\nkube-dns 10.96.0.10"]
        metallb["MetalLB\nspeaker DaemonSet\nVIP pool: 10.0.10.10-99"]
        ingress["ingress-nginx\nNetMlbVIP 10.0.10.10"]
    end

    subgraph external ["External"]
        client["External Client\n10.0.1.0/24"]
        nas["Synology NAS\n10.0.1.204"]
    end

    client -->|"HTTPS\n*.k8s.n37.ca"| metallb
    metallb --> ingress
    ingress -->|"backend Service"| kube_proxy
    kube_proxy -->|"DNAT to pod IP"| podA

    podC -->|"HBONE :15008\nmTLS"| zt1
    zt1 -->|"HBONE :15008"| podD

    podA -->|"DNS query"| coredns
    coredns -->|"upstream"| nas
```

## Path 1 — External client → backend service

```mermaid
sequenceDiagram
    participant C as External Client
    participant U as UDR (10.0.1.1)
    participant M as MetalLB (L2)
    participant N as Node holding VIP
    participant I as ingress-nginx pod
    participant S as Service ClusterIP
    participant P as Backend pod

    C->>U: DNS argocd.k8s.n37.ca → 10.0.10.10
    C->>M: TCP :443 → 10.0.10.10
    M->>N: ARP / GARP attracts traffic
    N->>I: Routes to ingress-nginx pod via kube-proxy iptables
    I->>I: TLS termination (or passthrough for argocd)
    I->>S: HTTP to argocd-server.argocd.svc:80
    S->>P: kube-proxy iptables DNAT → pod IP
    P-->>C: Response back through the same path (reverse NAT preserved)
```

**Key details:**

- MetalLB runs in L2 mode (chart 0.16.1 with `frrk8s.enabled: false`). One node at a time owns each VIP via gratuitous ARP. Failover takes ~10 seconds.
- ingress-nginx is the only L7 router. For services with `nginx.ingress.kubernetes.io/auth-url` (oauth2-proxy), nginx does the auth subrequest before forwarding.
- ArgoCD's ingress is **TLS passthrough**, so ingress-nginx forwards the encrypted bytes and argocd-server terminates TLS itself. Grafana's ingress terminates TLS at nginx and forwards HTTP.

## Path 2 — Pod-to-pod (Istio Ambient HBONE)

When both source and destination namespaces have `istio.io/dataplane-mode=ambient`, traffic is automatically wrapped in HBONE (HTTP/2-over-mTLS on port 15008).

```mermaid
sequenceDiagram
    participant SrcApp as Source pod (default ns)
    participant SrcZT as ztunnel on source node
    participant DstZT as ztunnel on destination node
    participant DstApp as Destination pod (argo-workflows ns)

    SrcApp->>SrcZT: TCP to argo-workflows-server.argo-workflows:2746
    Note over SrcZT: Intercept via traffic redirection
    SrcZT->>DstZT: HBONE encapsulated mTLS on :15008
    Note over SrcZT,DstZT: Identity: source SPIFFE / dest SPIFFE
    DstZT->>DstApp: Decrypt + forward to :2746
    DstApp-->>SrcApp: Response (reverse HBONE path)
```

**Key details:**

- ztunnel runs as a DaemonSet (one per node).
- HBONE adds mTLS automatically — no application-side change.
- NetworkPolicies need a bare port 15008 ingress AND egress rule on every meshed namespace, plus link-local `169.254.7.127/32` for ztunnel health probes.

### What happens at the boundary

If the destination is **NOT** meshed (e.g. `default → zot`), ztunnel falls back to **direct TCP** with the source pod IP as the literal sender. The destination NetworkPolicy then needs to allow the source pod explicitly — the bare HBONE rule on port 15008 is irrelevant.

```mermaid
sequenceDiagram
    participant SrcApp as Source pod (default ns, meshed)
    participant SrcZT as ztunnel on source node
    participant DstApp as Destination pod (zot ns, NOT meshed)

    SrcApp->>SrcZT: TCP to zot.zot:5000
    Note over SrcZT: Destination not in mesh registry
    SrcZT->>DstApp: Direct TCP (no HBONE) - source IP = pod IP
    Note over DstApp: NetworkPolicy sees pod IP as source<br/>Must allow blackbox-exporter explicitly
```

This is the gotcha that bit the SLO probe wiring in PRs #707 and #708 — see [Network Policies → Gotchas](../security/network-policies.md#hbone-bypass-requires-both-ends-ambient-meshed).

## Path 3 — Pod-to-MetalLB VIP (the hairpin)

Sometimes a workload resolves a service hostname like `argocd.k8s.n37.ca` and tries to reach the MetalLB VIP `10.0.10.10` from inside the cluster. This *mostly* doesn't work.

```mermaid
sequenceDiagram
    participant Pod as Pod (any ns)
    participant DNS as CoreDNS / upstream
    participant KP as kube-proxy on node
    participant VIP as MetalLB VIP 10.0.10.10
    participant I as ingress-nginx

    Pod->>DNS: Resolve argocd.k8s.n37.ca
    DNS-->>Pod: 10.0.10.10 (split-horizon DNS)
    Pod->>KP: Send TCP to 10.0.10.10:443

    Note over KP: KUBE-EXT-{svc} chain check<br/>--src-type LOCAL? NO<br/>(pod traffic is not LOCAL)
    Note over KP: No DNAT applied<br/>Packet leaves to node network
    KP-xVIP: Packet lost (no handler)
```

**Why this is broken.** kube-proxy installs a `KUBE-EXT-<svc>` iptables chain for every LoadBalancer Service. The chain only DNATs traffic where `--src-type` is `LOCAL` (= the node itself originated the packet). Pod traffic fails the LOCAL check, no DNAT happens, and the raw packet is routed to the node network where nothing answers.

**Workarounds:**

| Source pod type | Solution |
|---|---|
| Ambient-meshed pod, destination ingress backend is meshed | ztunnel HBONE bypasses kube-proxy — works |
| Ambient-meshed pod, destination is not meshed | Use ClusterIP DNS directly (`argocd-server.argocd:80`) |
| Non-meshed pod | Use ClusterIP DNS directly |

This is why Uptime Kuma monitors point at `http://argocd-server.argocd:80/healthz`, not `https://argocd.k8s.n37.ca/healthz`. And why SLO probes are split into an ingress-job (works for argocd/grafana) and a backend-job (works for everything via ClusterIP).

## Path 4 — Egress to upstream DNS / internet

```mermaid
sequenceDiagram
    participant Pod as Pod (any ns)
    participant CD as CoreDNS<br/>kube-dns 10.96.0.10
    participant NodeRes as Node /etc/resolv.conf
    participant UDR as UDR 10.0.1.1
    participant Up as Upstream<br/>(Cloudflare / Google)

    Pod->>CD: nslookup external.example
    CD->>CD: kubernetes plugin doesn't own this
    CD->>NodeRes: forward plugin<br/>uses /etc/resolv.conf
    NodeRes->>UDR: Recursive query
    UDR->>Up: Recursive forward
    Up-->>UDR: A record
    UDR-->>NodeRes: A record
    NodeRes-->>CD: A record
    CD-->>Pod: A record (cached 30s)
```

**Pod-to-internet TCP**: once the pod has the IP, traffic egresses via the node's default route → UDR → WAN. Calico does **not** NAT in IPIP mode for cross-cluster pod-to-pod — but pod-to-external traffic IS source-NAT'd to the node IP by the kernel's MASQUERADE.

See [CoreDNS](./coredns.md) for resolver details and [Cloudflare Tunnel](./cloudflare-tunnel.md) for the reverse direction (inbound public traffic without a port-forward).

## Where NetworkPolicies apply

NetworkPolicies are evaluated by Calico at the source's egress AND the destination's ingress — **both** sides must allow the path. The most common failure modes:

1. **Source egress allows it, destination ingress doesn't** — destination NetPol's missing.
2. **Destination ingress allows it, source egress only allows certain ports** — common with the `default` namespace which restricts egress to a specific port list (80, 443, 8443, 161, plus a few service-specific entries).
3. **Both are correct but the path uses an intermediate hop** — e.g. an HTTPS probe to ingress-nginx → backend service. The probe pod's egress must reach ingress-nginx; ingress-nginx's egress must reach the backend.

See [Network Policies → Gotchas](../security/network-policies.md#gotchas) for the worked examples.

## Related

- **[Network Overview](./overview.md)** — VLAN topology, switch/router/AP layout, MetalLB pool allocation
- **[CoreDNS](./coredns.md)** — Corefile, resolution patterns, troubleshooting
- **[Cloudflare Tunnel](./cloudflare-tunnel.md)** — inbound public traffic without a port-forward
- **[Istio Ambient Mesh](../applications/istio.md)** — HBONE protocol, ztunnel internals
- **[MetalLB](../applications/metallb.md)** — L2 announcer config, VIP pool
- **[Network Policies](../security/network-policies.md)** — full policy reference and gotchas
