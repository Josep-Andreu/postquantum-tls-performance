<div align="center">

# 🔐 Post-Quantum TLS: Beyond the Handshake

### What does quantum-resistant HTTPS *actually* cost?

**A reproducible performance study on Red Hat Enterprise Linux**  
OpenSSL · Apache HTTP Server · `wrk` · eBPF · Prometheus · Grafana

![Status](https://img.shields.io/badge/status-research%20in%20progress-2563eb?style=flat-square)
![Platform](https://img.shields.io/badge/platform-RHEL%209.8-ee0000?style=flat-square)
![Workload](https://img.shields.io/badge/workload-HTTPS-0f766e?style=flat-square)
![Runs](https://img.shields.io/badge/benchmark-5%20profiles%20%C3%97%205%20runs-6d28d9?style=flat-square)

**[The question](#the-question) · [Results](#first-results) · [Methodology](#how-we-measured) · [Observability](#seeing-beyond-http) · [Reproduce](#reproducing-the-experiments)**

</div>

---

> **The interesting question isn't whether post-quantum algorithms are slower in isolation.**  
> It's what happens to an HTTPS server when real connections, CPU pressure, and tail latency enter the picture.

## The question

Post-quantum cryptography (PQC) is moving from standards into deployed software. But an algorithm benchmark alone doesn't tell us how an application will behave under load.

This project investigates the operational cost of different TLS configurations by combining **application-level measurements** with **OpenSSL handshake tracing** and **host-level observability**.

We focus on three questions:

- **Throughput:** How many HTTPS requests per second can the server sustain?
- **Latency:** What happens to median and tail latency under sustained concurrency?
- **Visibility:** What can eBPF reveal about time spent inside `SSL_do_handshake`?

## First results

**October 28, 2026 retest · 5 rounds per profile · 120 seconds per run**

| TLS profile | HTTP requests/s (mean) | Change vs. `classic-a2` |
|:--|--:|--:|
| `classic-a2` | **1,879.51** | Baseline |
| `classic-c2` | 1,778.89 | −5.4% |
| `pqc-a1` | 1,485.11 | −21.0% |
| `pqc-b1` | 1,398.06 | −25.6% |
| `pqc-c1` | 1,397.83 | −25.6% |

**What stands out:** In this CPU-intensive HTTPS workload, the tested PQC configurations delivered approximately **21–26% fewer HTTP requests per second** than the `classic-a2` baseline.

These are **system-level observations**, not isolated cryptographic costs. The TLS profiles differ in their certificate and cryptographic configurations, so the differences must not be attributed to a single algorithm without further controls.

> [!IMPORTANT]
> These figures are preliminary results from one test environment. They are not universal predictions for production systems. Profile definitions and certificate chains should be verified against the final Apache/OpenSSL configuration before publication.

### At a glance

```text
HTTP requests per second · mean of five runs

classic-a2  ██████████████████████████████  1,880
classic-c2  ████████████████████████████    1,779
pqc-a1      ████████████████████████        1,485
pqc-b1      ██████████████████████          1,398
pqc-c1      ██████████████████████          1,398
```

*The bars are illustrative; use the raw CSV and generated figures for analysis.*

## How we measured

| Parameter | Configuration |
|:--|:--|
| Server OS | Red Hat Enterprise Linux 9.8 |
| TLS stack | OpenSSL 3.5.x + Apache HTTP Server |
| Load generator | `wrk` |
| Client concurrency | 50 connections |
| Load threads | 8 |
| Duration | 120 seconds per profile |
| Repetitions | 5 rounds, with varied execution order |
| Connection behavior | `Connection: close` to exercise fresh TLS connections |
| Instrumentation | eBPF tracing of OpenSSL `SSL_do_handshake` |
| Metrics | Prometheus + node exporter + custom TLS exporter |
| Visualization | Grafana + Python/Matplotlib |

The five profiles cover classical TLS and progressively different post-quantum configurations. The precise certificate, signature, and key-exchange parameters belong in [`docs/tls-profiles.md`](docs/tls-profiles.md), where they can be audited against the server configuration.

### Why five rounds?

A single benchmark can be misleading. We repeated each configuration five times and **changed the execution order between rounds** to reduce the influence of run order, warm-up, and time-dependent system behavior.

The test suite therefore contains **25 individual 120-second measurements** per battery, with timestamped `wrk` logs and corresponding Prometheus time windows.

## Seeing beyond HTTP

<img width="1774" height="887" alt="image" src="https://github.com/user-attachments/assets/1cef68e4-05da-4cf1-9d52-e6de85672aae" />


We examine complementary signals rather than relying on one number:

1. **`wrk`:** HTTP throughput and client-observed latency distributions.
2. **eBPF:** observed duration and rate of OpenSSL `SSL_do_handshake` calls.
3. **Host metrics:** CPU utilization during each benchmark window.
4. **Cross-run analysis:** means, dispersion, and consistency across rounds.

> [!NOTE]
> The eBPF duration of `SSL_do_handshake` is **not automatically equivalent** to the complete network-level TLS handshake time. It is an instrumented function duration and must be interpreted accordingly.

## Visualizing the trade-offs

The analysis generates seven dark-theme figures, suitable for technical articles and conference slides:

| Figure | What it explores |
|:--|:--|
| `01-throughput-dark` | Sustained HTTPS throughput |
| `02-ebpf-latency-dark` | OpenSSL handshake function latency |
| `03-cpu-dark` | CPU utilization |
| `04-throughput-vs-p99-dark` | Throughput versus tail latency |
| `05-reproducibility-dark` | Run-to-run variability |
| `06-relative-throughput-dark` | Relative throughput versus baseline |
| `07-wrk-latency-dark` | Client-observed HTTP latency |

Once committed, the plots can be embedded directly in this README from `figures/`.

## Repository layout

The following is the **proposed** structure as material is published:

```text
.
├── README.md
├── docs/
│   ├── architecture.md           # Testbed and measurement flow
│   ├── tls-profiles.md           # Audited TLS configuration matrix
│   ├── methodology.md           # Workload, ordering, limitations
│   └── findings.md              # Interpretation and conclusions
├── configs/
│   ├── apache/                  # Sanitized virtual-host examples
│   └── openssl/                 # Client-side OpenSSL profiles
├── scripts/
│   ├── benchmark/               # wrk runner and close.lua
│   ├── observability/           # TLS exporter and tracing setup
│   └── analysis/                # CSV extraction and plot scripts
├── results/
│   ├── 2026-10-09/              # Initial battery
│   └── 2026-10-28/              # Five-round retest
└── figures/                     # Publication-ready PNG / SVG / PDF
```

## Reproducing the experiments

The goal is to make the work **auditable and repeatable**, not merely to publish screenshots.

The benchmark runner selects one TLS profile at a time, labels the observability stream, allows a stabilization interval, and runs `wrk` with fresh HTTPS connections. The extraction step combines the timestamped `wrk` logs with Prometheus queries over the corresponding time window. The plotting step produces comparable figures across all five profiles.

**Detailed, copy-paste setup instructions will be added** as the configuration and scripts are sanitized and committed. Until then, treat this repository as an evolving research record rather than a turnkey benchmark suite.

## Reading the results responsibly

- **CPU saturation matters.** Results measured at high CPU utilization describe this particular bottleneck regime.
- **TLS profiles are not interchangeable.** Certificate algorithms, chains, and key exchange can all influence the outcome.
- **Latency tails matter.** A similar median does not imply similar p95 or p99 behavior.
- **Function tracing has boundaries.** An eBPF function measurement is not an end-to-end network measurement.
- **Repeatability matters.** Report the number of runs, their variability, and the precise workload.

## What's next

This repository currently focuses on the **first phase: classical versus post-quantum HTTPS performance**. The immediate priorities are publishing the sanitized configurations, raw benchmark logs, extraction scripts, and reproducible figures, followed by the full technical article.

---

<div align="center">

### 🔬 Beyond algorithms. Measure the system.

*Post-quantum TLS performance, observed from the HTTP client down to OpenSSL.*

</div>
