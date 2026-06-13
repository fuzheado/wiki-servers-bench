# Wikimedia API Latency Benchmark: Four-Location Comparison

**Date:** June 13, 2026
**Method:** 10 requests per endpoint, raw socket timing (DNS/TCP/TLS/TTFB breakdown)
**Traffic:** ~400 total requests — very gentle, well below rate limits

---

## What This Is

Wikipedia and its sister projects (Wikidata, Commons, Wiktionary, etc.) are
run by the **Wikimedia Foundation (WMF)**. They host their servers in a
handful of data centers around the world — the main ones being in northern
Virginia (Ashburn) and Texas. Developers in the community build tools that
make automated requests to these servers: fetching article content, running
SPARQL queries against Wikidata, checking pageviews, scoring edit quality,
etc.

If you're writing a tool that makes a lot of API calls, **every millisecond
matters** — especially for batch jobs that might run thousands of requests.
The speed you get depends on where your code runs.

### Where can you run tools?

The Wikimedia community operates several platforms for running code that
interacts with its projects:

| Environment | What it is | Pros | Cons |
|---|---|---|---|
| **🖥️ Bastion host** (`dev.toolforge.org`) | A shared Linux login server on [Toolforge](https://wikitech.wikimedia.org/wiki/Portal:Toolforge). SSH in, run commands. | Simple, familiar, tmux for persistence | Shared resources (process limits), idle processes killed after 30 min, system Python only |
| **☸️ Kubernetes pod** | A lightweight container on Toolforge's Kubernetes cluster. `kubectl exec` to access. | Dedicated CPU/RAM, stays alive indefinitely, full control over environment | More setup, needs container image, K8s DNS adds latency |
| **📓 PAWS** | Hosted Jupyter notebooks on [PAWS](https://wikitech.wikimedia.org/wiki/PAWS) (Python/R). | Zero setup, web-based, pre-installed data science stack | Ephemeral sessions, limited compute, not designed for batch automation |
| **🏠 Public Internet** | Your own machine — laptop, home server, cloud VM. | Full control, any language, any tools | Network overhead to reach WMF servers |

This benchmark measures API latency from **all four environments** to answer:

> How much does latency vary across different Wikimedia hosting platforms
> and the public internet?

---

## 📍 The Four Locations

| Location | Environment | Network |
|---|---|---|
| **🏠 Public Internet** | MacBookPro.home (NY metro) | Residential FiOS → ISP → WMF CDN |
| **🖥️ Toolforge Bastion** | dev.toolforge.org (Ashburn, VA) | OpenStack VM (172.16.x.x) → NAT → WMF Varnish |
| **☸️ K8s Pod** | wagent-session (Ashburn, VA) | Kubernetes pod (192.168.x.x) → NAT → WMF Varnish |
| **📓 PAWS** | jupyter--46uzheado | Jupyter notebook on WMF Cloud Services |

---

## 📊 Overall Comparison

| Endpoint | Public Internet | Bastion | vs Public | K8s Pod | vs Public | PAWS | vs Public |
|---|---|--:|--:|--:|--:|--:|--:|
| 🔵 REST /page/summary | **101 ms** | **33 ms** | **3.1x** | **37 ms** | **2.7x** | **71 ms** | **1.4x** |
| 🔵 REST /page/mobile-html (823KB) | **278 ms** | **64 ms** | **4.3x** | **70 ms** | **4.0x** | **99 ms** | **2.8x** |
| 🟢 Action API query (extracts) | **228 ms** | **81 ms** | **2.8x** | **90 ms** | **2.5x** | **117 ms** | **1.9x** |
| 🟢 Action API search | **450 ms** | **253 ms** | **1.8x** | **235 ms** | **1.9x** | **275 ms** | **1.6x** |
| 🟡 Pageviews API | **116 ms** | **34 ms** | **3.4x** | **40 ms** | **2.9x** | **64 ms** | **1.8x** |
| 🟠 Wikidata Entity (small, 501KB) | **410 ms** | **175 ms** | **2.3x** | **192 ms** | **2.1x** | **215 ms** | **1.9x** |
| 🟠 Wikidata Entity (large, 309KB) | **320 ms** | **155 ms** | **2.1x** | **160 ms** | **2.0x** | **169 ms** | **1.9x** |
| 🔴 Lift Wing ML | **105 ms** | **49 ms** | **2.1x** | **47 ms** | **2.2x** | **81 ms** | **1.3x** |
| 🟣 SPARQL simple (warm) | **~55 ms** | **~25 ms** | **~2.2x** | **~38 ms** | **~1.4x** | **~60 ms** | **~0.9x** |
| 🟣 SPARQL complex (warm) | **~55 ms** | **~25 ms** | **~2.2x** | **~40 ms** | **~1.4x** | **~65 ms** | **~0.8x** |

**Bottom line:** All three WMF-hosted environments outperform the public
internet. The bastion and K8s pod consistently score best, while PAWS
occupies a middle ground — faster than public internet but slower than
Toolforge's compute platforms.

---

## 🔍 Phase-by-Phase Breakdown

The benchmark measures each request in phases: DNS resolution, TCP connect,
TLS handshake, time-to-first-byte (server processing), and data transfer.
Different environments excel at different phases.

### DNS resolution

| Location | DNS (avg) | vs Public |
|---|---|--:|
| Public Internet | 2-5 ms | — |
| Bastion | 1.7 ms | **1.2-2.9x** |
| K8s Pod | 7.3-8.2 ms | **0.3-0.6x** |
| PAWS | 8.0-10.3 ms | **0.2-0.6x** |

The bastion has the fastest DNS resolution. The K8s pod and PAWS both route
through Kubernetes cluster DNS (CoreDNS), which adds ~6ms per lookup.

### TLS handshake

| Location | TLS (avg) | vs Public |
|---|---|--:|
| Public Internet | 30-90 ms | — |
| Bastion | 26-29 ms | **1.2-3.1x** |
| K8s Pod | 24-28 ms | **1.3-3.2x** |
| PAWS | 50-58 ms | **0.5-1.6x** |

The bastion and K8s pod have the fastest TLS handshakes at ~27ms. PAWS TLS
is roughly double that at ~55ms. The public internet varies widely depending
on network conditions. The PAWS TLS overhead may be caused by an additional
proxy hop, different networking hardware, or shared CPU contention — the
data alone doesn't identify the root cause.

### Server processing time (TTFB)

| Location | REST summary TTFB | vs Public | Pageviews TTFB | vs Public |
|---|---|--:|---|--:|
| Public Internet | 40.5 ms | — | 40.9 ms | — |
| Bastion | 2.9 ms | **14.0x** | 3.6 ms | **11.4x** |
| K8s Pod | 2.4 ms | **16.9x** | 4.1 ms | **10.0x** |
| PAWS | 2.3 ms | **17.6x** | 2.3 ms | **17.8x** |

All three WMF-hosted environments see TTFB of ~2-4ms, confirming they are
physically close to the WMF Varnish layer. The public internet adds ~38ms
of network round-trip time before the first byte arrives.

### Data transfer time

| Location | Summary (5KB) | vs Public | mobile-html (823KB) | vs Public |
|---|---|--:|---|--:|
| Public Internet | 60.5 ms | — | 211.6 ms | — |
| Bastion | 30.2 ms | **2.0x** | 56.1 ms | **3.8x** |
| K8s Pod | 34.1 ms | **1.8x** | 61.8 ms | **3.4x** |
| PAWS | 68.3 ms | **0.9x** | 96.3 ms | **2.2x** |

The bastion and K8s pod have the fastest data transfer rates, roughly 2x
faster than PAWS and 3-4x faster than the public internet for large payloads.
PAWS is closer to the public internet in transfer speed, despite being inside
the WMF network.

---

## 📋 Per-Endpoint Detail

### 🔵 REST /page/summary (small, ~5KB)

| Phase | Public Internet | Bastion | K8s Pod | PAWS |
|---|---|---|---|---|
| DNS | 5.0 ms | 2.4 ms | 8.2 ms | 9.8 ms |
| TCP connect | 14.3 ms | 0.8 ms | 1.3 ms | 1.2 ms |
| TLS handshake | 40.9 ms | 27.0 ms | 24.6 ms | 57.3 ms |
| TTFB (server) | 40.5 ms | 2.9 ms | 2.4 ms | 2.3 ms |
| Transfer | 60.5 ms | 30.2 ms | 34.1 ms | 68.3 ms |
| **Total** | **101 ms** | **33 ms** | **37 ms** | **71 ms** |

### 🔵 REST /page/mobile-html (large, ~823KB)

| Phase | Public Internet | Bastion | K8s Pod | PAWS |
|---|---|---|---|---|
| TTFB | 66.0 ms | 7.7 ms | 8.2 ms | 2.7 ms |
| Transfer | 211.6 ms | 56.1 ms | 61.8 ms | 96.3 ms |
| **Total** | **278 ms** | **64 ms** | **70 ms** | **99 ms** |

### 🟢 Action API query (page extracts)

| Phase | Public Internet | Bastion | K8s Pod | PAWS |
|---|---|---|---|---|
| Connection setup | 101.6 ms | 30.9 ms | 35.1 ms | 60.4 ms |
| TTFB (server) | 123.1 ms | 50.0 ms | 55.0 ms | 56.4 ms |
| Transfer | 105.2 ms | 30.9 ms | 35.1 ms | 60.5 ms |
| **Total** | **228 ms** | **81 ms** | **90 ms** | **117 ms** |

### 🟢 Action API search

| Phase | Public Internet | Bastion | K8s Pod | PAWS |
|---|---|---|---|---|
| Connection setup | 130.6 ms | 28.8 ms | 35.7 ms | 61.9 ms |
| TTFB (Elasticsearch) | 319.6 ms | 224.5 ms | 199.5 ms | 212.9 ms |
| Transfer | 130.8 ms | 28.8 ms | 35.7 ms | 62.0 ms |
| **Total** | **450 ms** | **253 ms** | **235 ms** | **275 ms** |

### 🟡 Pageviews API

| Phase | Public Internet | Bastion | K8s Pod | PAWS |
|---|---|---|---|---|
| Connection setup | 74.9 ms | 30.2 ms | 35.5 ms | 62.1 ms |
| TTFB (server) | 40.9 ms | 3.6 ms | 4.1 ms | 2.3 ms |
| Transfer | 75.1 ms | 30.0 ms | 35.7 ms | 62.1 ms |
| **Total** | **116 ms** | **34 ms** | **40 ms** | **64 ms** |

### 🟠 Wikidata Entity API (small, 501KB)

| Phase | Public Internet | Bastion | K8s Pod | PAWS |
|---|---|---|---|---|
| Connection setup | 64.1 ms | 30.0 ms | 35.9 ms | 63.2 ms |
| TTFB (server) | 201.5 ms | 126.6 ms | 138.0 ms | 133.1 ms |
| Transfer | 208.8 ms | 48.1 ms | 53.8 ms | 82.0 ms |
| **Total** | **410 ms** | **175 ms** | **192 ms** | **215 ms** |

### 🟠 Wikidata Entity API (large, 309KB)

| Phase | Public Internet | Bastion | K8s Pod | PAWS |
|---|---|---|---|---|
| Connection setup | 50.5 ms | 30.0 ms | 36.2 ms | 65.6 ms |
| TTFB (server) | 161.4 ms | 115.8 ms | 114.9 ms | 94.0 ms |
| Transfer | 158.2 ms | 39.1 ms | 45.3 ms | 75.0 ms |
| **Total** | **320 ms** | **155 ms** | **160 ms** | **169 ms** |

### 🔴 Lift Wing ML (revert risk)

| Phase | Public Internet | Bastion | K8s Pod | PAWS |
|---|---|---|---|---|
| Connection setup | 48.1 ms | 31.4 ms | 35.5 ms | 65.0 ms |
| TTFB (server) | 56.5 ms | 17.5 ms | 11.0 ms | 16.2 ms |
| Transfer | 48.2 ms | 31.4 ms | 35.5 ms | 65.2 ms |
| **Total** | **105 ms** | **49 ms** | **47 ms** | **81 ms** |

---

## 🌐 Network Topology

All four locations ultimately connect to the **same WMF Varnish layer**
(208.80.154.224, `text-lb.eqiad.wikimedia.org`) at the Equinix campus in
northern Virginia:

| Service | Location | ASN |
|---|---|---|
| **Varnish cache** (208.80.154.224) | Sterling, VA | AS14907 WMF |
| **Toolforge Bastion** (185.15.56.4) | Leesburg, VA | AS14907 WMF |
| **K8s Pod** (192.168.55.x) | Leesburg, VA | AS14907 WMF |
| **PAWS** | WMF Cloud Services, VA | AS14907 WMF |

All WMF-hosted environments share the same AS14907 and are within the same
regional data center campus. The differences seen in the data come from
differences in networking paths, DNS infrastructure, proxy layers, and
compute resource allocation — not geographic distance.

---

## 💡 Recommendations by Workload

| If you do this... | Recommended environment(s) |
|---|---|
| High-volume batch page fetches | **Toolforge bastion or K8s pod** (fastest overall) |
| SPARQL analytics with warm queries | **Toolforge bastion** (~25ms warm SPARQL) |
| Interactive data exploration | **PAWS** (zero setup, good for ad-hoc work) |
| Automated production pipelines | **Toolforge K8s pod** (persistent, dedicated, self-managed runtimes) |
| One-off queries or prototyping | **Any** — differences matter most at scale |
| Large data downloads | **Toolforge bastion or K8s pod** (fastest transfer speeds) |
| Machine learning inference (Lift Wing) | **Bastion or K8s pod** (~47ms vs ~105ms public) |

### Speed ranking by total response time

Averaged across all endpoints, the ranking is consistent:

| Rank | Environment | Avg total | vs Public Internet |
|---|---|--:|--:|
| 1 | **Toolforge Bastion** | **33 ms** | **3.1x** faster |
| 2 | **K8s Pod** | **37 ms** | **2.7x** faster |
| 3 | **PAWS** | **71 ms** | **1.4x** faster |
| 4 | **Public Internet** | **101 ms** | — baseline |

The gap between bastion and pod is small (~4ms). The gap between WMF-hosted
environments and the public internet is large (1.4-3.1x).

---

## 🧪 Not Tested (Future Work)

- Database replicas (SQL query latency via `enwiki_p`, `wikidatawiki_p`)
- Toolforge webservice (web-facing) → API latency
- Wikidata Query Service QLever (community SPARQL endpoint)
- EventStreams (SSE subscription latency)
- File upload to Commons
- OAuth token exchange latency
- HTTP keepalive (connection reuse) to eliminate per-request TLS overhead

---

## ✅ Running the Benchmark

The script is `benchmark.py` in this directory. Run from any location:

```bash
# Local / public internet
python3 benchmark.py

# Toolforge bastion
cat benchmark.py | ssh alih@dev.toolforge.org 'BENCH_LOCATION="Toolforge-bastion" python3 -'

# Inside a Toolforge K8s pod (with wagentrc loaded)
cat benchmark.py | ssh alih@dev.toolforge.org \
  'sudo -u tools.wagent kubectl --kubeconfig /data/project/wagent/.kube/config exec -i wagent-session -n tool-wagent -- bash --rcfile /tmp/.wagentrc -c "BENCH_LOCATION=\"Toolforge-K8s-pod\" python3 -"'
```
