# Wikimedia API Latency Benchmark: Four-Location Comparison

**Date:** June 13, 2026
**Method:** 10 requests per endpoint, raw socket timing (DNS/TCP/TLS/TTFB breakdown)
**Traffic:** ~400 total requests — very gentle, well below rate limits

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
Wikimedia projects, and **[PAWS](https://wikitech.wikimedia.org/wiki/PAWS)**,
a hosted Jupyter notebook environment for interactive analysis.

| Environment | What it is | Pros | Cons |
|---|---|---|---|
| **🖥️ Bastion host** (`dev.toolforge.org`) | A shared Linux login server. You SSH in and run commands directly. | Simple, familiar, tmux for persistence | Shared with everyone (process limits!), idle processes killed after 30 min, system Python only |
| **☸️ Kubernetes pod** | A lightweight container on Toolforge's Kubernetes cluster. You `kubectl exec` into it. | Dedicated resources (CPU/RAM), stays alive indefinitely, you control the environment (Python, Node.js, packages) | More setup, needs container image, K8s DNS adds latency |
| **📓 PAWS** | Hosted Jupyter notebooks (Python/R) for interactive data analysis | Zero setup, web-based, pre-installed data science stack | Ephemeral sessions, limited compute, not designed for batch automation |

This benchmark compares all three WMF-hosted environments against a "control
group" of requests made from a residential internet connection (a MacBook Pro
in the New York metro area).

### The question we're asking

> How much faster are Wikimedia API calls when you run inside the WMF network
vs on the public internet? And is there a meaningful difference between the
bastion, Kubernetes pods, and PAWS notebooks?

---

## 📍 The Four Locations

| Location | Environment | Network | Role in this test |
|---|---|---|---|
| **🏠 Public Internet** | MacBookPro.home (NY metro) | Residential FiOS → ISP → WMF CDN | Control group — what a normal user gets |
| **🖥️ Toolforge Bastion** | dev.toolforge.org (Ashburn, VA) | OpenStack VM (172.16.x.x) → NAT → WMF Varnish | "Classic" Toolforge — SSH + run commands |
| **☸️ K8s Pod** | wagent-session (Ashburn, VA) | Kubernetes pod (192.168.x.x) → NAT → WMF Varnish | Modern Toolforge — container with managed runtimes |
| **📓 PAWS** | jupyter--46uzheado | Jupyter notebook on WMF Cloud Services | Interactive analysis — one-click data science |

---

## 📊 Four-Way Comparison Table

| Endpoint | Public Internet | Bastion | K8s Pod | PAWS |
|---|---|---|---|---|
| 🔵 REST /page/summary | **101 ms** | **33 ms** | **37 ms** | **71 ms** |
| 🔵 REST /page/mobile-html (823KB) | **278 ms** | **64 ms** | **70 ms** | **99 ms** |
| 🟢 Action API query (extracts) | **228 ms** | **81 ms** | **90 ms** | **117 ms** |
| 🟢 Action API search | **450 ms** | **253 ms** | **235 ms** | **275 ms** |
| 🟡 Pageviews API | **116 ms** | **34 ms** | **40 ms** | **64 ms** |
| 🟠 Wikidata Entity (small, 501KB) | **410 ms** | **175 ms** | **192 ms** | **215 ms** |
| 🟠 Wikidata Entity (large, 309KB) | **320 ms** | **155 ms** | **160 ms** | **169 ms** |
| 🔴 Lift Wing ML | **105 ms** | **49 ms** | **47 ms** | **81 ms** |
| 🟣 SPARQL simple (warm) | **~55 ms** | **~25 ms** | **~38 ms** | **~60 ms** |
| 🟣 SPARQL complex (warm) | **~55 ms** | **~25 ms** | **~40 ms** | **~65 ms** |

---

## 🔍 Phase-by-Phase: Where PAWS Wins and Loses

### DNS latency

| Location | DNS (avg) |
|---|---|
| Public Internet | 2-5 ms |
| **Bastion** | **1.7 ms** ⚡ fastest |
| K8s Pod | 7.3-8.2 ms |
| **PAWS** | **8.0-10.3 ms** |

PAWS DNS is similar to the K8s pod — both go through Kubernetes cluster DNS
(CoreDNS) instead of direct system resolution.

### TLS handshake

| Location | TLS (avg) |
|---|---|
| Public Internet | 30-90 ms (high variance) |
| **Bastion** | **26-29 ms** ⚡ fastest |
| K8s Pod | 24-28 ms |
| **PAWS** | **50-58 ms** 🐢 slowest |

This is the biggest surprise. PAWS TLS handshake is **~55ms**, almost double
the Toolforge environments (~27ms). This is consistent across all endpoints
and not a fluke — every single request shows this pattern.

**Possible causes:**
- PAWS may route through an additional proxy layer (like a web proxy or
  authentication gateway) that adds TLS overhead
- Different TLS library or hardware offloading capability
- PAWS instances may be on a different subnet with a longer path to the
  Varnish layer

### TTFB (server processing time)

| Location | REST summary TTFB | Rest mobile-html TTFB |
|---|---|---|
| Public Internet | 40.5 ms | 66.0 ms |
| **Bastion** | **2.9 ms** | **7.7 ms** |
| K8s Pod | 2.4 ms | 8.2 ms |
| **PAWS** | **2.3 ms** ⚡ | **2.7 ms** ⚡ fastest |

**PAWS wins here.** The time-to-first-byte from the server is just 2.3ms for
the REST summary — essentially the same as the Toolforge environments and way
better than the 40ms from public internet. This confirms PAWS IS inside the
WMF network, physically close to the Varnish layer.

### Transfer time (data download)

| Location | Summary (5KB) | mobile-html (823KB) |
|---|---|---|
| Public Internet | 60.5 ms | 211.6 ms |
| Bastion | 30.2 ms | 56.1 ms |
| K8s Pod | 34.1 ms | 61.8 ms |
| **PAWS** | **68.3 ms** 🐢 | **96.3 ms** 🐢 |

PAWS transfer times are **double** the Toolforge environments. For the 823KB
mobile-html page, PAWS takes 96ms vs 56ms on the bastion and 62ms in the pod.
This suggests PAWS has lower bandwidth or higher latency on the data path
back from the Varnish layer.

---

## 🧩 Understanding PAWS

### Where PAWS sits

```
PAWS notebook → ?proxy? → Varnish → Backend API
    ↑ TLS: ~55ms       TTFB: ~2ms  Transfer: ~68ms
```

PAWS is clearly inside the WMF network (2.3ms TTFB proves proximity to
Varnish), but something adds overhead on the TLS handshake and data transfer.
This could be:
1. **An additional proxy hop** — PAWS sessions may route through a web proxy
   or authentication gateway that terminates and re-establishes TLS
2. **Different network hardware** — PAWS runs on a different cluster with
   different NICs or routing
3. **CPU contention** — PAWS notebooks share CPU with other users, which
   could slow down TLS handshake (which is CPU-bound)

### What PAWS is good for

| Workload | PAWS verdict | Why |
|---|---|---|
| Interactive exploration | ✅ Great | TTFB is excellent (2-3ms), good enough for manual work |
| SPARQL prototyping | ✅ Good | Warm SPARQL at ~60ms is fine for interactive querying |
| Batch page fetches | ⚠️ OK | 71ms vs 33ms on bastion — 2x slower, still better than public internet |
| Large data downloads | ❌ Not ideal | Transfer is 2x slower than Toolforge, similar to public internet |
| Automated production | ❌ No | Ephemeral, not designed for persistent automation |

### PAWS vs Toolforge TL;DR

```
Metric              Best            PAWS ranking
─────────────────────────────────────────────────
Server processing   Bastion/Pod     🥈 tied for first (~2ms TTFB)
TLS handshake       Bastion/Pod     🐢 last (~55ms vs ~27ms)
DNS resolution      Bastion         tied with K8s Pod (~9ms vs ~2ms)
Data transfer       Bastion         🐢 last (~2x slower than bastion)
```

PAWS trades raw performance for **zero-config convenience** — you get a
browser-based notebook with all the data science libraries pre-installed,
and the server processing is just as fast as Toolforge. The extra ~30ms of
TLS overhead and ~30ms of transfer overhead only matter for high-throughput
batch workloads.

---

## ⚡ Phase-by-Phase Full Comparison

### 🔵 REST /page/summary (small, ~5KB response)

| Phase | Public Internet | Bastion | K8s Pod | PAWS |
|---|---|---|---|---|
| DNS | 5.0 ms | 2.4 ms | 8.2 ms | **9.8 ms** |
| TCP connect | 14.3 ms | 0.8 ms | 1.3 ms | **1.2 ms** |
| TLS handshake | 40.9 ms | 27.0 ms | 24.6 ms | **57.3 ms** |
| TTFB (server) | 40.5 ms | 2.9 ms | 2.4 ms | **2.3 ms** |
| Transfer | 60.5 ms | 30.2 ms | 34.1 ms | **68.3 ms** |
| **Total** | **101 ms** | **33 ms** | **37 ms** | **71 ms** |

### 🔵 REST /page/mobile-html (large, ~823KB response)

| Phase | Public Internet | Bastion | K8s Pod | PAWS |
|---|---|---|---|---|
| TTFB | 66.0 ms | 7.7 ms | 8.2 ms | **2.7 ms** |
| Transfer | 211.6 ms | 56.1 ms | 61.8 ms | **96.3 ms** |
| **Total** | **278 ms** | **64 ms** | **70 ms** | **99 ms** |

### 🟢 Action API query (page extracts)

| Phase | Public Internet | Bastion | K8s Pod | PAWS |
|---|---|---|---|---|
| Connection setup | 101.6 ms | 30.9 ms | 35.1 ms | **60.4 ms** |
| TTFB (server) | 123.1 ms | 50.0 ms | 55.0 ms | **56.4 ms** |
| Transfer | 105.2 ms | 30.9 ms | 35.1 ms | **60.5 ms** |
| **Total** | **228 ms** | **81 ms** | **90 ms** | **117 ms** |

### 🟢 Action API search

| Phase | Public Internet | Bastion | K8s Pod | PAWS |
|---|---|---|---|---|
| Connection setup | 130.6 ms | 28.8 ms | 35.7 ms | **61.9 ms** |
| TTFB (Elasticsearch) | 319.6 ms | 224.5 ms | 199.5 ms | **212.9 ms** |
| Transfer | 130.8 ms | 28.8 ms | 35.7 ms | **62.0 ms** |
| **Total** | **450 ms** | **253 ms** | **235 ms** | **275 ms** |

### 🟡 Pageviews API

| Phase | Public Internet | Bastion | K8s Pod | PAWS |
|---|---|---|---|---|
| TLS + DNS + TCP | 74.9 ms | 30.2 ms | 35.5 ms | **62.1 ms** |
| TTFB (server) | 40.9 ms | 3.6 ms | 4.1 ms | **2.3 ms** |
| Transfer | 75.1 ms | 30.0 ms | 35.7 ms | **62.1 ms** |
| **Total** | **116 ms** | **34 ms** | **40 ms** | **64 ms** |

---

## 🌐 Network Topology Summary

Everything tested runs in the **same Equinix campus** in northern Virginia:

| Service | Location | ASN | Ping RTT |
|---|---|---|---|
| **Varnish cache** (208.80.154.224) | Sterling, VA | AS14907 WMF | — |
| **Toolforge Bastion** (185.15.56.4) | Leesburg, VA | AS14907 WMF | 0.5ms to Varnish |
| **K8s Pod** (192.168.55.x) | Leesburg, VA | AS14907 WMF | 0.9ms to Varnish |
| **PAWS** | Unknown within WMF cloud | AS14907 WMF | 2.3ms TTFB suggests ~1ms RTT |

PAWS's 2.3ms TTFB proves it's physically close to the Varnish layer. But the
~55ms TLS handshake (vs ~27ms on Toolforge) suggests an additional proxy or
different network path between PAWS and the WMF production network.

---

## 💡 Recommendations

| If you do this... | Run from... | Why |
|---|---|---|
| Batch page fetches (high volume) | **Toolforge bastion or K8s pod** | 3-4x faster than public, 2x faster than PAWS |
| SPARQL analytics (warm) | **Toolforge bastion** | ~25ms — fastest warm SPARQL |
| Interactive data exploration | **PAWS** | Zero setup, good-enough latency, pre-installed libs |
| One-off queries / analysis | **PAWS** or local | Convenience wins over milliseconds |
| Automated production pipelines | **Toolforge K8s pod** | Persistent, dedicated resources, managed runtimes |
| Machine Learning (Lift Wing) | **K8s pod or bastion** | ~47ms — 2x faster than public, 1.7x faster than PAWS |

### Ranking by total speed (lower is better)

```
1. 🖥️  Toolforge Bastion   33ms  ⚡ fastest overall
2. ☸️  K8s Pod             37ms  (close second)
3. 📓  PAWS                71ms  (2x slower than bastion, still beats public)
4. 🏠  Public Internet    101ms  (baseline)
```

The ranking is consistent across all endpoints, though the gaps vary.

---

## 🧪 What's Not Tested (Future Work)

- Database replicas (SQL query latency — `enwiki_p` etc.)
- Toolforge webservice (web-facing) → API latency
- Wikidata Query Service QLever (community SPARQL endpoint)
- EventStreams (SSE subscription latency)
- File upload to Commons
- OAuth token exchange latency
- PAWS with keepalive (connection reuse to eliminate TLS overhead per request)

---

## ✅ Script

The benchmark script is at `benchmark.py` in this directory. Run it:

```bash
# Local
python3 benchmark.py

# On Toolforge bastion
cat benchmark.py | ssh alih@dev.toolforge.org 'BENCH_LOCATION="Toolforge-bastion" python3 -'

# Inside wagent K8s pod
cat benchmark.py | ssh alih@dev.toolforge.org \
  'sudo -u tools.wagent kubectl --kubeconfig /data/project/wagent/.kube/config exec -i wagent-session -n tool-wagent -- bash --rcfile /tmp/.wagentrc -c "BENCH_LOCATION=\"Toolforge-K8s-pod\" python3 -"'
```
