# November 4, 2026 — TLS benchmark stability campaign

Supplementary, reproducible results for **Post-Quantum TLS: Beyond the Handshake**.

## Experimental design

- Five TLS profiles × five independent rounds = **25 runs**, each **120 seconds**.
- `wrk -t8 -c50 -d120s --latency -s close.lua` (HTTP `Connection: close`, forcing new connections).
- Balanced/varied profile order between rounds, 30-second per-profile warm-up and 60-second wait following exporter restart/profile-label change.
- Server: RHEL 9.8, 4 vCPU, Apache httpd 2.4.62, OpenSSL 3.5.8, event MPM.
- Client: RHEL 9.8, 8 vCPU, custom PQC-capable `wrk` build.
- Observability: Prometheus 3.13.1, Grafana 10.2.6, bpftrace 0.24.2 and node exporter; Prometheus scrape interval 1 second.
- Campaign window: 2026-11-04 15:50:57–17:05:10 UTC.

| Label | TLS configuration | Server port |
|---|---|---:|
| CLASSIC A.2 | ECDSA P-384; secp384r1 | 8443 |
| CLASSIC C.2 | ECDSA P-521; secp521r1 | 9443 |
| PQC A.1 | X25519MLKEM768; ML-DSA-65 | 10443 |
| PQC B.1 | X25519MLKEM768; ML-DSA-65 authentication; SLH-DSA-SHA2-192s certificate signature | 11443 |
| PQC C.1 | MLKEM1024; ML-DSA-87 | 12443 |

## Data

- `pqc_results_stability.csv`: one row per run, `wrk` throughput, HTTP p50/p99, CPU and eBPF-derived quantiles (25 rows).
- `pqc_cpu_stability.csv`: per-run CPU utilization, estimated from the final ~90 seconds, using ten 10-second-step Prometheus samples and a 30-second rate window (25 rows).
- `pqc_histogram_buckets_stability.csv`: per-run cumulative Prometheus histogram bucket increases, 21 buckets per run (525 rows).

The eBPF percentiles in the plots are **pooled across five runs per profile**, derived by interpolating cumulative histogram buckets. Error bars on percentile plots represent **±1 sample standard deviation of run-level interpolated percentiles**, not confidence intervals. Fractional bucket increases reflect Prometheus `increase()` extrapolation. A successful `SSL_do_handshake()` function call may be only part of a nonblocking handshake; its wall-clock duration is **not** pure cryptographic CPU time, nor necessarily complete end-to-end TLS negotiation.

CPU utilization near 100% is consistent with saturation, but does not isolate the cryptographic contribution. Results represent this connection-heavy, no-resumption test configuration; they should not be generalized to keep-alive or session-resumption workloads.

## Recreate figures

From the repository root, with Python 3, `matplotlib` and `numpy` installed:

Run from the repository root:

```bash
python3 scripts/plot-dark-stability.py
```

The script reads the three CSVs from `benchmarks/2026-11-04-stability/` automatically.

Outputs: `scripts/figures/dark/` (seven figures, PNG/PDF/SVG). Committed preview images are under `figures/2026-11-04-stability/`.

Dependencies: `python3 -m pip install matplotlib numpy` (prefer a virtual environment). For exact figures, preserve fonts and Matplotlib versions used in the original campaign.

## Interpretation

The mean throughput reductions relative to CLASSIC A.2 were 4.2% (CLASSIC C.2), 18.6% (PQC A.1), 23.4% (PQC B.1), and 24.6% (PQC C.1). All profiles ran with server CPU utilization around 98–99%. The figures show a consistent separation between classical and PQC profiles, but the sample size (five runs/profile) does not establish statistical significance between the PQC configurations.

These files contain processed metrics, not original raw `wrk` logs or raw Prometheus time series. The extraction scripts and raw campaign logs should be published separately after checking the originals.
