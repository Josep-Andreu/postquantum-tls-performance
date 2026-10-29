<div align="center">

# 🔐 Post-Quantum TLS: Beyond the Handshake

### **What does quantum-resistant HTTPS actually cost?**

**An experimental performance study on Red Hat Enterprise Linux**

`OpenSSL 3.5` · `Apache HTTP Server` · `wrk` · `eBPF` · `Prometheus` · `Grafana`

![RHEL](https://img.shields.io/badge/RHEL-9.8-EE0000?style=for-the-badge)
![TLS](https://img.shields.io/badge/TLS-1.3-2563EB?style=for-the-badge)
![Runs](https://img.shields.io/badge/Benchmark-25_runs-7C3AED?style=for-the-badge)
![Status](https://img.shields.io/badge/Status-Experimental-F59E0B?style=for-the-badge)

**[Results](#-the-results-first) · [Why it matters](#-why-this-matters) · [Architecture](#-inside-the-lab) · [Methodology](#-how-we-tested) · [Reproduce](#-reproducing-the-study)**

</div>

---

## The results, first

> **In our CPU-saturated HTTPS testbed, the post-quantum TLS profiles delivered approximately 21–26% fewer requests per second than the classical A.2 baseline.**
>
> That's an observed *system-level* difference—not a universal PQC overhead figure or an isolated cryptographic benchmark.

<div align="center">

| **PQC A.1** | **PQC B.1** | **PQC C.1** |
|:---:|:---:|:---:|
| **−21.0%** | **−25.6%** | **−25.6%** |
| HTTP throughput | HTTP throughput | HTTP throughput |
| vs. `classic-a2` | vs. `classic-a2` | vs. `classic-a2` |

*October 28, 2026 · 5 runs/profile · 120 seconds/run · 8 threads · 50 concurrent connections*

</div>

### HTTP throughput under sustained load

| Profile | Scenario | Mean requests/s | vs. classical A.2 |
|:--|:--|--:|--:|
| **`classic-a2`** | A.2 · classical baseline | **1,879.51** | **Baseline** |
| `classic-c2` | C.2 · classical | 1,778.89 | −5.4% |
| `pqc-a1` | A.1 · post-quantum | 1,485.11 | −21.0% |
| `pqc-b1` | B.1 · post-quantum | 1,398.06 | −25.6% |
| `pqc-c1` | C.1 · post-quantum | 1,397.83 | −25.6% |

```text
Mean HTTP requests/s · October 28 retest · 5 runs per profile

classic-a2  ██████████████████████████████  1,880
classic-c2  ████████████████████████████    1,779
pqc-a1      ████████████████████████        1,485
pqc-b1      ██████████████████████          1,398
pqc-c1      ██████████████████████          1,398
```

*Text bars are approximate. The numeric table is authoritative; publication-ready Matplotlib figures will be added alongside the raw data.*

### But throughput is only half the story

The same experiment also measures **client-observed HTTP latency**, **time spent in OpenSSL's `SSL_do_handshake`**, **handshake rate**, and **server CPU utilization**.

| Profile | Mean eBPF handshake calls/s | Mean server CPU |
|:--|--:|--:|
| `classic-a2` | 1,841.54 | 96.80% |
| `classic-c2` | 1,744.32 | 96.83% |
| `pqc-a1` | 1,451.89 | 97.43% |
| `pqc-b1` | 1,368.60 | 97.58% |
| `pqc-c1` | 1,371.52 | 97.72% |

*Means from five per-run Prometheus extractions. CPU values describe this testbed under sustained load; eBPF call rates are not independently verified successful network handshakes.*

**The question is not just how fast a PQC primitive executes. It's what happens to an HTTPS server when fresh TLS connections, concurrent clients, and CPU pressure meet.**

---

## 🔎 Why this matters

Post-quantum cryptography is becoming available in mainstream TLS stacks. But a microbenchmark of a signature or key-encapsulation operation cannot, by itself, predict application behavior.

This repository studies the performance of **a complete HTTPS workload** while exposing what happens inside the TLS implementation:

- **Application perspective:** requests per second and latency measured by `wrk`.
- **TLS perspective:** duration and frequency of `SSL_do_handshake` calls observed using eBPF.
- **Host perspective:** CPU utilization collected by Prometheus.
- **Experimental perspective:** repeated runs, rotated execution order, timestamped logs, and traceable CSV outputs.

**Scope:** classical and post-quantum **server-side HTTPS/TLS**. This phase deliberately excludes mutual TLS, proxies, and Kubernetes.

---

## 🧭 Inside the lab

<img width="1774" height="887" alt="image" src="https://github.com/user-attachments/assets/ddf5d8a7-1f62-4966-844c-57e38f0972b4" />


*The diagram illustrates the experimental workflow and intended scenario matrix. Cryptographic profile details in the diagram must be audited against the actual server certificates and negotiated TLS parameters before being treated as verified implementation facts.*

The measurement path is straightforward:

**`wrk` client → Apache/OpenSSL on RHEL → eBPF + node exporter → Prometheus → Python analysis → figures**

The key idea is to connect **what clients experience** with **what the TLS library and host are doing**.

### The five profiles

Our benchmark names map to the following **reference scenarios**:

| Benchmark name | Reference scenario | Intended key exchange | Intended digital signature |
|:--|:--|:--|:--|
| `pqc-a1` | A.1 · PQC Enterprise DSA | `X25519MLKEM768` | `ML-DSA-65` |
| `classic-a2` | A.2 · Classical Enterprise ECDSA | NIST P-384 | ECDSA with SHA-384 |
| `pqc-b1` | B.1 · PQC Enterprise FIPS 205 | `X25519MLKEM768` | `SLH-DSA-SHA2-192s` |
| `pqc-c1` | C.1 · PQC CNSA 2.0 | `ML-KEM-1024` | `ML-DSA-87` |
| `classic-c2` | C.2 · Classical CNSA 2.0 | NIST P-521 | ECDSA with SHA-512 |

> [!WARNING]
> **Reference scenarios ≠ verified live configurations.** In particular, earlier lab descriptions associated `pqc-b1` with ML-DSA-65, whereas the reference scenario above specifies SLH-DSA-SHA2-192s. We must inspect the deployed certificates, chains, OpenSSL configuration, and negotiated TLS groups before claiming exact algorithm-level comparisons. The benchmark measurements remain labeled by their actual test profile names.

---

## 🧪 How we tested

| Setting | Value |
|:--|:--|
| HTTPS server | Apache HTTP Server on RHEL 9.8 |
| Cryptographic library | OpenSSL 3.5.x |
| Client | `wrk` |
| Threads | `8` |
| Concurrent connections | `50` |
| Test duration | `120 seconds` |
| Repetitions | `5` per profile |
| Total tests per battery | **25** |
| Connection reuse | Disabled with `Connection: close` |
| Profile order | Rotated between rounds |
| TLS tracing | eBPF instrumentation of `SSL_do_handshake` |
| Host metrics | Prometheus / node exporter |
| Data processing | Python, CSV, Matplotlib |

Simplified load-generator invocation:

```bash
wrk -t8 -c50 -d120s --latency -s close.lua \
  https://<server>:<profile-port>/
```

The actual runner also selects the corresponding OpenSSL client configuration, switches the observability profile, waits for stabilization, and records UTC start/end timestamps.

### Why five rounds?

We avoid drawing conclusions from a single benchmark. Each profile was tested five times, with its position rotated between rounds to reduce systematic run-order effects. **Run-to-run variation still matters** and should be reported alongside averages.

### How the metrics were joined

1. Parse timestamped `wrk` logs for HTTP throughput and latency.
2. Query historical Prometheus metrics within each test's time window, trimming five seconds at either end.
3. Compute eBPF latency percentiles and CPU metrics from Prometheus time series.
4. Consolidate five rounds into a 25-row CSV.
5. Generate comparative figures from the consolidated dataset.

The original extraction script uses 10-second Prometheus `rate()` windows and 1-second query steps. These choices are part of the methodology, not incidental implementation details.

---

## 📊 Visualizations

The analysis pipeline produces seven dark-theme figures:

| Figure | Question answered |
|:--|:--|
| `01-throughput-dark` | How many HTTPS requests/s can each profile sustain? |
| `02-ebpf-latency-dark` | How does `SSL_do_handshake` duration change? |
| `03-cpu-dark` | How busy is the server? |
| `04-throughput-vs-p99-dark` | What is the relationship between throughput and tail latency? |
| `05-reproducibility-dark` | How stable are results across five runs? |
| `06-relative-throughput-dark` | How does each profile compare with the baseline? |
| `07-wrk-latency-dark` | What latency does the client observe? |

**Planned:** commit the actual PNG/SVG plots from the October 28 retest and link them here. We do not substitute illustrative plots for measured data.

---

## 📁 Repository structure

The directories below describe the **target layout** as scripts and datasets are published:

```text
.
├── README.md
├── assets/
│   └── tls-benchmark-workflow.png
├── docs/
│   ├── architecture.md
│   ├── tls-profiles.md
│   ├── methodology.md
│   └── findings.md
├── configs/
│   ├── apache/
│   └── openssl/
├── scripts/
│   ├── benchmark/       # wrk runner and close.lua
│   ├── observability/   # eBPF TLS exporter
│   └── analysis/        # extract.py and plot-dark.py
├── results/
│   ├── 2026-10-09/      # Original benchmark battery
│   └── 2026-10-28/      # Retest: 25 runs
└── figures/
    └── 2026-10-28/      # Real plots (to be added)
```

## 🛠️ Reproducing the study

This repository is being assembled as an **auditable experimental record**, not a one-command performance claim.

To reproduce the study, you will need the Apache virtual-host and certificate configurations, the matching OpenSSL client profiles, the `wrk` runner and `close.lua`, the eBPF exporter, Prometheus scrape configuration, and the CSV/plotting scripts.

**Configuration files, commands, raw logs, and figures will be added after sanitization.** No production credentials, private keys, or internal hostnames should be committed.

---

## ⚠️ Interpreting the results

- **Not a universal PQC penalty:** these are measurements of five specific TLS configurations on one system.
- **Not a single-variable comparison:** key exchange, certificate signature, chain, and negotiated parameters may differ.
- **CPU is near saturation:** the numbers describe a particular high-load regime.
- **eBPF function time is not end-to-end TLS time:** `SSL_do_handshake` measurements do not automatically represent the complete client-visible handshake.
- **The benchmark is connection-heavy:** disabling connection reuse intentionally emphasizes TLS setup cost.
- **The retest is a separate dataset:** do not pool October 9 and October 28 runs without explaining the differences in conditions.

---

<div align="center">

### **Beyond algorithms. Measure the system.**

*From HTTPS throughput to the TLS implementation itself.*

</div>
