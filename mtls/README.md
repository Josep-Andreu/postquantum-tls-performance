# Mutual TLS (mTLS): Classic, Hybrid and Post-Quantum Authentication

**Historical RHEL mTLS experiment — October 2026.** Part of [Post-Quantum TLS: Beyond the Handshake](https://github.com/Josep-Andreu/postquantum-tls-performance).

This directory preserves a nine-run, three-profile mTLS performance campaign and the scripts needed to audit its published files and regenerate its eight figures. It is a separate campaign from the main repository's November 4 **server-authenticated HTTPS** benchmark; numerical results must **not** be pooled across campaigns.

> **Interpretation:** Results compare complete TLS configurations on a specific, near-CPU-saturated 4-vCPU server. They do not show that ML-KEM or ML-DSA primitives are intrinsically faster than classical algorithms. The dataset alone does not independently prove certificate-chain validation or verify that eBPF counts map one-to-one to completed TLS handshakes.

## Three measured profiles

| Profile | Port in lab | Server authentication | Client authentication | TLS 1.3 key exchange |
| --- | --- | --- | --- | --- |
| **Classic** | 13443 | ECDSA P-384 | ECDSA P-384 | `secp384r1` |
| **Hybrid** | 15443 | ECDSA P-384 | ECDSA P-384 | `X25519MLKEM768` |
| **PQC authentication** | 14443 | ML-DSA-65 | ML-DSA-65 | `X25519MLKEM768` |

The "PQC" profile refers to *post-quantum authentication with hybrid key establishment*. It is **not** a purely post-quantum key exchange: X25519 is still a classical component.

All nine provided client logs report TLS 1.3 with `TLS_AES_256_GCM_SHA384`, 8 worker threads, 50 concurrent connections and a 120-second duration. They report zero resumed sessions. The client prints the negotiated group, server public-key algorithm and the path of a configured client certificate, but the archive does not contain the actual OpenSSL/Apache validation evidence or the `wrk` patch source required to verify every authentication behavior independently.

## Observed results

| Metric (mean of three runs per profile) | Classic | Hybrid | PQC authentication |
| --- | ---: | ---: | ---: |
| HTTP requests/s | **946.68** | **1,100.47** | **1,027.75** |
| HTTP client p99 (ms) | 161.25 | 206.24 | 161.07 |
| eBPF-observed `SSL_do_handshake()` call mean (ms) | 39.01 | 31.99 | 36.51 |
| eBPF-observed call p50 (ms) | 26.86 | 17.76 | 22.06 |
| eBPF-observed call p99 (ms) | 198.99 | 200.80 | 213.14 |
| Total server CPU busy (%) | 96.57 | 96.34 | 96.33 |
| Server CPU-s per 1,000 recorded full handshakes | 4.076 | 3.498 | 3.745 |

Hybrid delivered **+16.25%** more HTTP requests/s than Classic in this specific test, and the PQC-authentication profile delivered **+8.56%**. However, Hybrid also showed **approximately 27.9% higher client-observed p99 HTTP request latency** than Classic. Better throughput does not imply uniformly better latency.

All CPU-efficiency numbers are **total server CPU time per recorded full handshake**, not isolated cryptographic CPU consumption. The eBPF percentiles are means of three *per-run* histogram quantile estimates, **not** percentiles calculated by pooling raw event durations.

## Repository contents

- `data/*.log`: nine **sanitized** historical `wrk` outputs (hostnames and absolute client-cert paths replaced; numerical results preserved).
- `data/round1.csv`, `data/rounds2-3.csv`: pre-aggregated eBPF measurements and *historical* CPU fields; the `cpu_percent` values in these two files came from a different 130-second window and should not be used for the final CPU figures.
- `data/cpu-120s.csv`: CPU breakdown for the **exact 120-second measurement windows**, used for published CPU plots.
- `results/mtls-consolidated.csv`: nine-row eBPF summary used by the plotting script.
- `results/runs.csv` and `results/summary.csv`: machine-readable derived tables, recomputed from the included logs/CSV input.
- `scripts/consolidate-mtls.py`: original consolidation logic with a portable path.
- `scripts/plot-mtls-dark.py`: original eight-figure plotting logic with a portable path.
- `scripts/verify-mtls.py`: offline internal-consistency checks.
- `figures/dark/`: eight historical figures in PNG, SVG and PDF.
- `docs/methodology-and-limitations.md`: reproducibility scope and missing validation evidence.
- `docs/next-experiments.md`: follow-up experimental design.

## Reproduce the included figures (offline)

From the **repository root**:

```bash
python3 mtls/scripts/verify-mtls.py
python3 -m venv .venv
source .venv/bin/activate
pip install -r mtls/requirements.txt
python mtls/scripts/consolidate-mtls.py
python mtls/scripts/plot-mtls-dark.py
```

The last command creates all eight figure types in PNG/PDF/SVG below `mtls/figures/dark/`. The scripts no longer require `/root/pqc-benchmark-results/...` and do not contact Prometheus.

These commands **regenerate plots from derived data**. They do **not** reproduce the original live TLS benchmarks nor regenerate the historical eBPF histogram quantiles from raw Prometheus metrics. See [limitations and missing artifacts](docs/methodology-and-limitations.md) before drawing strong causal conclusions.

## Recommended next step

1. Recover and publish **sanitized** Apache VirtualHosts / TLS configuration, `wrk-mtls` source or patch, and eBPF exporter code.
2. Verify mTLS failure modes, certificate chains, hostname validation, and handshakes-versus-call counting.
3. Add an ECDSA P-384 / `X25519` control profile, keeping authentication material identical to the Hybrid profile, then rerun with varying load and more randomized rounds.

**Never publish private keys, PATs, unredacted internal endpoint addresses, or client credentials.**
