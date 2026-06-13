#!/usr/bin/env python3
"""
Wikimedia API Latency Benchmark
Compares latency of various Wikimedia API endpoints.
Run from: (1) local/residential internet, (2) Toolforge bastion
"""

import json
import os
import socket
import ssl
import sys
import time
import statistics
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ITERATIONS = 10       # per endpoint — small, gentle, proof-of-concept
DELAY = 0.5           # seconds between requests (be polite)
USER_AGENT = "WikiBenchmark/1.0 (https://github.com/fuzheado; alih@fuzheado.com) WikiServerBench"

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class TimingResult:
    dns: float = 0.0
    connect: float = 0.0
    tls: float = 0.0
    ttfb: float = 0.0
    total: float = 0.0
    status: int = 0
    size: int = 0
    error: Optional[str] = None

@dataclass
class EndpointResult:
    name: str
    url: str
    runs: list = field(default_factory=list)

    def add(self, r: TimingResult):
        self.runs.append(r)

    @property
    def ok_runs(self):
        return [r for r in self.runs if r.error is None]

    def summary(self) -> dict:
        ok = self.ok_runs
        if not ok:
            return {"name": self.name, "error": "all requests failed"}
        return {
            "name": self.name,
            "count": len(ok),
            "total_ms": {
                "min": round(min(r.total for r in ok) * 1000, 1),
                "max": round(max(r.total for r in ok) * 1000, 1),
                "mean": round(statistics.mean(r.total for r in ok) * 1000, 1),
                "stdev": round(statistics.stdev(r.total for r in ok) * 1000, 2) if len(ok) > 1 else 0,
            },
            "dns_ms": {
                "mean": round(statistics.mean(r.dns for r in ok) * 1000, 1),
            },
            "connect_ms": {
                "mean": round(statistics.mean(r.connect for r in ok) * 1000, 1),
            },
            "tls_ms": {
                "mean": round(statistics.mean(r.tls for r in ok) * 1000, 1),
            },
            "ttfb_ms": {
                "mean": round(statistics.mean(r.ttfb for r in ok) * 1000, 1),
            },
            "transfer_ms": {
                "mean": round(statistics.mean(r.total - r.ttfb for r in ok) * 1000, 1),
            },
            "avg_response_size_bytes": round(statistics.mean(r.size for r in ok)),
        }

# ---------------------------------------------------------------------------
# Timed HTTP request with connection-level breakdown
# ---------------------------------------------------------------------------

def timed_request(url: str) -> TimingResult:
    """Make ONE HTTP GET and break down timing by connection phase."""
    import urllib.request as req_lib

    result = TimingResult()
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    t0 = time.time()

    try:
        # --- DNS ---
        t_dns_start = time.time()
        addrs = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
        addr = addrs[0][4]
        result.dns = time.time() - t_dns_start

        # --- TCP connect ---
        t_conn_start = time.time()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(15)
        sock.connect(addr)
        result.connect = time.time() - t_conn_start

        # --- TLS handshake ---
        t_tls_start = time.time()
        context = ssl.create_default_context()
        tls_sock = context.wrap_socket(sock, server_hostname=host)
        result.tls = time.time() - t_tls_start

        # --- HTTP request + response (measure TTFB) ---
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query
        request = ("GET " + path + " HTTP/1.1\r\n"
                   f"Host: {host}\r\n"
                   f"User-Agent: {USER_AGENT}\r\n"
                   "Accept: */*\r\n"
                   "Connection: close\r\n"
                   "\r\n")
        t_req_start = time.time()
        tls_sock.sendall(request.encode())

        # Read headers for TTFB
        response_data = b""
        while True:
            chunk = tls_sock.recv(4096)
            if not chunk:
                break
            response_data += chunk
            if b"\r\n\r\n" in response_data:
                result.ttfb = time.time() - t_req_start
                # Continue reading the rest
                break

        # Read remaining body
        while True:
            chunk = tls_sock.recv(8192)
            if not chunk:
                break
            response_data += chunk

        result.total = time.time() - t0
        result.size = len(response_data)

        # Parse status line
        headers_end = response_data.find(b"\r\n\r\n")
        status_line = response_data[:response_data.find(b"\r\n")].decode("utf-8", errors="replace")
        parts = status_line.split(" ")
        result.status = int(parts[1]) if len(parts) >= 2 else 0

        tls_sock.close()

    except Exception as e:
        result.total = time.time() - t0
        result.error = str(e)

    return result

# ---------------------------------------------------------------------------
# Endpoint definitions
# ---------------------------------------------------------------------------

def get_endpoints() -> list[dict]:
    """Returns list of {name, url} dicts."""
    return [
        {
            "name": "🔵 REST /page/summary (small payload)",
            "url": "https://en.wikipedia.org/api/rest_v1/page/summary/Albert%20Einstein",
        },
        {
            "name": "🔵 REST /page/mobile-html (large payload)",
            "url": "https://en.wikipedia.org/api/rest_v1/page/mobile-html/Albert%20Einstein",
        },
        {
            "name": "🟢 Action API query (extracts)",
            "url": "https://en.wikipedia.org/w/api.php?action=query&prop=extracts&exintro&explaintext&titles=Albert%20Einstein&format=json",
        },
        {
            "name": "🟢 Action API search",
            "url": "https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch=Albert%20Einstein&format=json&srlimit=10",
        },
        {
            "name": "🟣 SPARQL (simple query)",
            "url": "https://query.wikidata.org/sparql?format=json&query=SELECT%20%3Fitem%20%3FitemLabel%20WHERE%20%7B%20%3Fitem%20wdt%3AP31%20wd%3AQ5.%20%3Fitem%20wdt%3AP106%20wd%3AQ169470.%20SERVICE%20wikibase%3Alabel%20%7B%20bd%3AserviceParam%20wikibase%3Alanguage%20%22en%22.%20%7D%20%7D%20LIMIT%2010",
        },
        {
            "name": "🟣 SPARQL (complex query)",
            "url": "https://query.wikidata.org/sparql?format=json&query=SELECT%20%3Fitem%20%3FitemLabel%20%3FbirthDate%20WHERE%20%7B%20%3Fitem%20wdt%3AP31%20wd%3AQ5.%20%3Fitem%20wdt%3AP106%20wd%3AQ169470.%20%3Fitem%20wdt%3AP569%20%3FbirthDate.%20FILTER%28YEAR%28%3FbirthDate%29%20%3E%201900%29%20%7D%20ORDER%20BY%20%3FbirthDate%20LIMIT%2050",
        },
        {
            "name": "🟡 Pageviews API",
            "url": "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/all-agents/Albert_Einstein/daily/20250101/20250107",
        },
        {
            "name": "🟠 Wikidata Entity API (small entity)",
            "url": "https://www.wikidata.org/wiki/Special:EntityData/Q937.json",
        },
        {
            "name": "🟠 Wikidata Entity API (large entity)",
            "url": "https://www.wikidata.org/wiki/Special:EntityData/Q42.json",
        },
        {
            "name": "🔴 Lift Wing ML (revert risk)",
            "url": "https://api.wikimedia.org/service/lw/inference/v1/models/revertrisk-language-agnostic:predict",
        },
    ]

# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_benchmark(endpoints: list[dict], location: str) -> list[EndpointResult]:
    """Run all endpoints (respects DELAY between requests)."""
    print(f"\n{'='*70}")
    print(f"🧪 WIKIMEDIA API BENCHMARK — Running from: {location}")
    print(f"   Iterations per endpoint: {ITERATIONS}")
    print(f"   Delay between requests:  {DELAY}s")
    print(f"{'='*70}\n")

    results = []
    for ep in endpoints:
        name = ep["name"]
        url = ep["url"]
        er = EndpointResult(name=name, url=url)

        print(f"  ⏳ {name}")
        for i in range(ITERATIONS):
            r = timed_request(url)
            er.add(r)
            status_line = f"    [{i+1}/{ITERATIONS}]"
            if r.error:
                status_line += f" ❌ {r.error}"
            else:
                status_line += f" ✅ {r.status} | total={r.total*1000:.0f}ms | ttfb={r.ttfb*1000:.0f}ms | dns={r.dns*1000:.1f}ms | tcp={r.connect*1000:.1f}ms | tls={r.tls*1000:.1f}ms | {r.size} bytes"
            print(status_line)

            if i < ITERATIONS - 1:
                time.sleep(DELAY)

        # Show quick summary for this endpoint
        summary = er.summary()
        if "error" in summary:
            print(f"  ❌ ALL FAILED: {summary['error']}")
        else:
            s = summary
            print(f"  ✓ mean={s['total_ms']['mean']}ms | ttfb={s['ttfb_ms']['mean']}ms | "
                  f"dns={s['dns_ms']['mean']}ms | tcp={s['connect_ms']['mean']}ms | "
                  f"tls={s['tls_ms']['mean']}ms | xfer={s['transfer_ms']['mean']}ms | "
                  f"size={s['avg_response_size_bytes']}b")
        print()

        results.append(er)

    return results


def print_summary_table(all_results: dict[str, list[EndpointResult]]):
    """Print a side-by-side comparison table."""
    print(f"\n{'='*100}")
    print("📊 COMPARISON TABLE: Toolforge vs Public Internet")
    print(f"{'='*100}\n")

    # Align results by endpoint name
    locations = list(all_results.keys())
    first_loc = locations[0]
    others = locations[1:]

    header = f"{'Endpoint':<50}"
    for loc in locations:
        header += f" | {'Avg (ms)':<10}  {'TTFB(ms)':<10}"
    header += f" | {'Speedup':<10}"
    print(header)
    print("-" * len(header))

    for i, ep_name in enumerate(r.name for r in all_results[first_loc]):
        row_sums = {}
        row_errors = {}
        for loc in locations:
            er = all_results[loc][i]
            s = er.summary()
            if "error" in s:
                row_errors[loc] = s["error"]
            else:
                row_sums[loc] = s

        if first_loc in row_errors:
            display_name = f"  ❌ {ep_name[:46]}"
            print(f"{display_name:<50}" + " | error" * len(locations))
            continue

        display_name = ep_name[:48]
        row = f"{display_name:<50}"
        for loc in locations:
            s = row_sums.get(loc)
            if s:
                row += f" | {s['total_ms']['mean']:<10}  {s['ttfb_ms']['mean']:<10}"
            else:
                row += f" | {'ERR':<10}  {'ERR':<10}"
        # Speedup: first location / second location
        if len(locations) >= 2 and first_loc in row_sums and others[0] in row_sums:
            speedup = row_sums[others[0]]["total_ms"]["mean"] / row_sums[first_loc]["total_ms"]["mean"]
            row += f" | {speedup:.1f}x{' slower' if speedup > 1 else ' faster'}"
        print(row)

    print()


def print_detailed_summary(all_results: dict[str, list[EndpointResult]]):
    """Print per-location JSON summary."""
    for location, results in all_results.items():
        print(f"\n📋 DETAILED: {location}")
        print(json.dumps([r.summary() for r in results], indent=2))
        print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import urllib.parse

    location = os.environ.get("BENCH_LOCATION", socket.gethostname() or "unknown")

    endpoints = get_endpoints()

    # Run benchmarks
    results = run_benchmark(endpoints, location)

    # Print detailed JSON
    print_detailed_summary({location: results})

    # If we have a comparison file, load it and show side-by-side
    compare_file = os.environ.get("BENCH_COMPARE")
    if compare_file and os.path.exists(compare_file):
        with open(compare_file) as f:
            other_data = json.load(f)
        other_results = [EndpointResult(name=e["name"], url="") for e in endpoints]
        # Rehydrate
        for i, ep in enumerate(other_results):
            ep.runs = [TimingResult(**r) for r in other_data[i].get("runs", [])]
            er = other_data[i]
            ep.runs = [TimingResult(**r) for r in er.get("runs", [])]
            ep.url = er.get("url", "")

        all_results = {location: results, other_data.get("_location", "other"): other_results}
        print_summary_table(all_results)
