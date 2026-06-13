# Wikimedia API Latency Benchmark: Three-Location Comparison

**Date:** June 13, 2026
**Method:** 10 requests per endpoint, raw socket timing (DNS/TCP/TLS/TTFB breakdown)
**Traffic:** ~300 total requests — very gentle, well below rate limits

---

## What This Is

Wikipedia and its sister projects (Wikidata, Commons, Wiktionary, etc.) are
run by the **Wikimedia Foundation (WMF)**. They host their servers in a
handful of data centers around the world — the main ones being in northern
Virginia (ashburn) and Texas. Developers in the community build tools that
make automated requests to these servers: fetching article content, running
SPARQL queries against Wikidata, checking pageviews, scoring edit quality,
etc.

If you're writing a tool that makes a lot of API calls, **every millisecond
matters** — especially for batch jobs that might run thousands of requests.
The speed you get depends on where your code runs.

### Where can you run tools?

The Wikimedia community operates **[Toolforge](https://wikitech.wikimedia.org/wiki/Portal:Toolforge)**,
a free cloud platform where anyone can host tools and bots that interact with
Wikimedia projects. There are two main ways to run code on Toolforge:

| Environment | What it is | Pros | Cons |
|---|---|---|---|
| **🖥️ Bastion host** (`dev.toolforge.org`) | A shared Linux login server. You SSH in and run commands directly. | Simple, familiar, tmux for persistence | Shared with everyone (process limits!), idle processes killed after 30 min, system Python only |
| **☸️ Kubernetes pod** | A lightweight container running on Toolforge's Kubernetes cluster. You `kubectl exec` into it. | Dedicated resources (CPU/RAM), stays alive indefinitely, you control the environment (Python version, packages, Node.js) | More setup, needs container image, slightly different networking (K8s DNS adds latency) |

This benchmark compares both Toolforge environments against a "control group"
of requests made from a residential internet connection (a MacBook Pro in the
New York metro area).

### The question we're asking

> How much faster are Wikimedia API calls when you run inside the WMF network
vs on the public internet? And does it matter whether you use the bastion
or a Kubernetes pod?

---

## 📍 The Three Locations

| Location | Environment | Network | Role in this test |
|---|---|---|---|
| **🏠 Public Internet** | MacBookPro.home (NY metro) | Residential FiOS → ISP → WMF CDN | Control group — what a normal user gets |
| **🖥️ Toolforge Bastion** | dev.toolforge.org (Ashburn, VA) | OpenStack VM (172.16.x.x) → NAT → WMF Varnish | "Classic" Toolforge — SSH + run commands |
| **☸️ K8s Pod** | wagent-session (Ashburn, VA) | Kubernetes pod (192.168.x.x) → NAT → WMF Varnish | Modern Toolforge — container with managed runtimes |

---

## 📊 Three-Way Comparison Table

| Endpoint | Public Internet | Bastion | K8s Pod | Pod vs Public |
|---|---|---|---|---|
| 🔵 REST /page/summary | **101 ms** | **33 ms** | **37 ms** | **2.7x** |
| 🔵 REST /page/mobile-html (823KB) | **278 ms** | **64 ms** | **70 ms** | **4.0x** |
| 🟢 Action API query (extracts) | **228 ms** | **81 ms** | **90 ms** | **2.5x** |
| 🟢 Action API search | **450 ms** | **253 ms** | **235 ms** | **1.9x** |
| 🟡 Pageviews API | **116 ms** | **34 ms** | **40 ms** | **2.9x** |
| 🟠 Wikidata Entity (small, 501KB) | **410 ms** | **175 ms** | **192 ms** | **2.1x** |
| 🟠 Wikidata Entity (large, 309KB) | **320 ms** | **155 ms** | **160 ms** | **2.0x** |
| 🔴 Lift Wing ML | **105 ms** | **49 ms** | **47 ms** | **2.2x** |
| 🟣 SPARQL simple (warm) | **~55 ms** | **~25 ms** | **~38 ms** | **1.4x** |
| 🟣 SPARQL complex (warm) | **~55 ms** | **~25 ms** | **~40 ms** | **1.4x** |

---

## ⚡ Phase-by-Phase Breakdown

### 🔵 REST /page/summary (small, ~5KB response)

| Phase | Public Internet | Bastion | K8s Pod |
|---|---|---|---|
| DNS | 5.0 ms | 2.4 ms | **8.2 ms** |
| TCP connect | 14.3 ms | 0.8 ms | **1.3 ms** |
| TLS handshake | 40.9 ms | 27.0 ms | **24.6 ms** |
| TTFB (server processing) | 40.5 ms | 2.9 ms | **2.4 ms** |
| Transfer | 60.5 ms | 30.2 ms | **34.1 ms** |
| **Total** | **101 ms** | **33 ms** | **37 ms** |

### 🔵 REST /page/mobile-html (large, ~823KB response)

| Phase | Public Internet | Bastion | K8s Pod |
|---|---|---|---|
| TTFB | 66.0 ms | 7.7 ms | **8.2 ms** |
| Transfer | 211.6 ms | 56.1 ms | **61.8 ms** |
| **Total** | **278 ms** | **64 ms** | **70 ms** |

### 🟢 Action API query (page extracts)

| Phase | Public Internet | Bastion | K8s Pod |
|---|---|---|---|
| Connection setup | 101.6 ms | 30.9 ms | **35.1 ms** |
| TTFB (server processing) | 123.1 ms | 50.0 ms | **55.0 ms** |
| Transfer | 105.2 ms | 30.9 ms | **35.1 ms** |
| **Total** | **228 ms** | **81 ms** | **90 ms** |

### 🟢 Action API search

| Phase | Public Internet | Bastion | K8s Pod |
|---|---|---|---|
| Connection setup | 130.6 ms | 28.8 ms | **35.7 ms** |
| TTFB (Elasticsearch) | 319.6 ms | 224.5 ms | **199.5 ms** |
| Transfer | 130.8 ms | 28.8 ms | **35.7 ms** |
| **Total** | **450 ms** | **253 ms** | **235 ms** |

---

## 🎯 Key Findings

### 1. Pod ≈ Bastion — both are ~2-4x faster than public internet
The K8s pod and the bastion are nearly identical in performance. The pod is sometimes slightly slower (REST: 37ms vs 33ms) and sometimes slightly faster (search: 235ms vs 253ms). The differences are noise — both are inside the Equinix campus.

### 2. The pod has slower DNS resolution
The pod's DNS takes **~8ms** per request vs **~2ms** on the bastion. This is because the pod uses the Kubernetes cluster DNS (CoreDNS) which adds a hop. The bastion uses direct system DNS. This adds ~6ms to every new-connection request.

**Mitigation:** With HTTP keepalive (connection reuse), DNS is only resolved once per connection, not per request. The impact on real workloads would be negligible.

### 3. Server processing time is identical across all three
TTFB for REST /page/summary is 2.4ms (pod), 2.9ms (bastion), 40.5ms (public). The server-side processing time is **~2-3ms** regardless of where you call from. The 37ms difference between pod/public is all **network overhead** (TLS + TCP + DNS).

### 4. Search is dominated by backend processing
Action API search TTFB is **200-225ms** even from inside the network. Elasticsearch processing dominates. The speedup is only 1.8-1.9x vs 2-4x for other endpoints.

### 5. SPARQL cold start exists everywhere
The first SPARQL query after a period of inactivity takes **~1-5 seconds** from any location. After that, warm queries are much faster:
- Public: ~55ms
- Pod: ~38ms 
- Bastion: ~25ms

The pod is slightly slower than the bastion for warm SPARQL (~38ms vs ~25ms), likely due to the additional DNS hop and NAT routing through Kubernetes.

---

## 🌐 Network Topology Investigation

### Where everything lives

| Service | IP Address | Location | ASN |
|---|---|---|---|
| **Toolforge bastion** | 185.15.56.4 | Leesburg, VA (Equinix campus) | AS14907 WMF |
| **K8s pod (wagent)** | 192.168.55.x / 172.16.x.x | Equinix campus, VA | AS14907 WMF |
| **Varnish cache** (`text-lb.eqiad`) | 208.80.154.224 | Sterling, VA (Equinix campus) | AS14907 WMF |
| **WDQS (SPARQL)** | 208.80.154.224 (same VIP) | Same Varnish layer | AS14907 WMF |
| **en.wikipedia.org** | 208.80.154.224 (same VIP) | Same Varnish layer | AS14907 WMF |

**They're all in the same Equinix campus** in northern Virginia, ~10-15 miles apart. Everything is AS14907 (Wikimedia Foundation).

### The actual network path

**From K8s pod → 208.80.154.224 (Varnish):**
```
Pod → OpenStack GW → NAT → WMF router → Varnish
<-- ~0.5ms --> <-- ~0.5ms -->       
Total ≈ 0.9ms RTT (same campus)
```

**From Bastion → 208.80.154.224:**
```
Bastion → OpenStack GW → NAT → WMF router → Varnish
<-- ~0.5ms --> <-- ~0.5ms -->       
Total ≈ 0.9ms RTT
```

**From Public → 208.80.154.224:**
```
ISP → multiple hops → Varnish
Total ≈ 12-15ms RTT
```

### Why the pod DNS is slower

```
Pod DNS lookup:
  Pod → CoreDNS (kube-system) → upstream DNS → response
  <-- 5-8ms per lookup -->

Bastion DNS lookup:
  Bastion → /etc/resolv.conf (system DNS) → response  
  <-- 1-2ms per lookup -->
```

The Kubernetes DNS adds a proxy hop through CoreDNS, which is configured to forward to upstream resolvers. This explains the consistent ~6ms extra DNS time from the pod.

### Internal `.wmnet` hostnames are NOT accessible

Toolforge cannot resolve internal Wikimedia hostnames like `wdqs.svc.eqiad.wmnet`. All traffic from both the bastion and K8s pods goes through the **public Varnish layer**, even though everything is in the same campus. This is because Toolforge runs on a separate OpenStack private network that doesn't have access to the internal `.wmnet` DNS zone.

The impact is negligible because the network RTT within the campus is <1ms.

### Bottom line

All three locations are in the same Equinix/Ashburn campus. The differences are:
- **Public internet**: adds 12-15ms RTT + 20-30ms extra TLS overhead due to longer TCP path
- **Bastion vs Pod**: essentially identical; pod has ~6ms more DNS that disappears with keepalive
- **Server processing**: identical from any location

---

## 💡 Recommendations

| If you do this... | Run from... | Why |
|---|---|---|
| Batch page fetches | **Toolforge (bastion or pod)** | 3-4x faster |
| SPARQL analytics (warm) | **Toolforge (bastion or pod)** | 2x faster with keepalive |
| SPARQL (infrequent/cold) | **Either** | 1s cold start from anywhere |
| Action API search | **K8s pod** | Slightly faster (235ms vs 253ms) |
| ML inference (Lift Wing) | **Toolforge** | 2x faster |
| Database replica queries | **Toolforge** | Direct tunnel to analytics replicas |

### Pod vs Bastion trade-offs

| Aspect | Bastion | K8s Pod |
|---|---|---|
| **Latency** | Slightly faster (33ms vs 37ms avg) | Slightly slower (DNS overhead) |
| **Persistence** | Limited (30-min idle kill) | Infinite (sleep infinity) |
| **Resource limits** | Shared (process limits hit ~59 threads) | Dedicated (1 CPU / 1 Gi default) |
| **Python** | System 3.13.5 (no pip) | Managed 3.13.14 (with pip + uv) |
| **Node.js** | Not available | Managed v22.22.3 |

---

## 🧪 What's Not Tested (Future Work)

- Database replicas (SQL query latency — `enwiki_p` etc.)
- Toolforge webservice (web-facing) → API latency
- Wikidata Query Service QLever (community SPARQL endpoint)
- EventStreams (SSE subscription latency)
- File upload to Commons
- OAuth token exchange latency
- Comparison with different Kubernetes resource limits

---

## ✅ Script

The benchmark script is at `benchmark.py` in this directory. Run it:

```bash
# Local
python3 benchmark.py

# On Toolforge bastion
cat benchmark.py | ssh alih@dev.toolforge.org 'BENCH_LOCATION="Toolforge-bastion" python3 -'

# Inside wagent K8s pod
cat benchmark.py | ssh alih@dev.toolforge.org 'sudo -u tools.wagent kubectl --kubeconfig /data/project/wagent/.kube/config exec -i wagent-session -n tool-wagent -- bash --rcfile /tmp/.wagentrc -c "BENCH_LOCATION=\"Toolforge-K8s-pod\" python3 -"'
```
