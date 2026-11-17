# mTLS experiment: methodology and limitations

## Source measurements and reproduction

The nine-run mTLS campaign was conducted on RHEL 9.8, Apache HTTP Server 2.4.62 and OpenSSL 3.5.8 (4-vCPU server). A custom mTLS-capable `wrk` client was used with 8 threads, 50 connections, 120-second runs, 3 rounds and distinct TLS 1.3 profiles. The uploaded audit archive contains nine human-readable client logs, pre-aggregated eBPF results, 120-second CPU metrics and eight original figures.

`data/runs.csv` combines the exact numbers transcribed from the logs and the consolidated/CPU CSVs; `data/summary.csv` contains means of three runs. The original raw logs and the original chart files are **not** in this initial GitHub branch; see `missing-artifacts.md`.

## Recorded evidence versus independently validated facts

Each historical `wrk` log prints a client certificate path, the negotiated group and a client-side counter line `full=N resumed=0 total=N`. The logs report 1,108,144 complete handshakes and no resumed connections. The uploaded PDF also asserts agreement between client and eBPF counters, but raw Prometheus time series, exact query windows, the eBPF counting implementation and the mTLS `wrk` source code have **not been provided**. Therefore, agreement between independent sources and exact completed-handshake semantics cannot yet be verified from the published CSV alone.

The project still needs explicit positive and negative certificate-authentication tests: no client certificate, wrong-CA cert, invalid/expired cert, invalid server hostname, and a full trust-chain/EKU check, plus source review of `SSL_VERIFY_PEER`, `SSL_set1_host()` and the custom `wrk` handshake counters.

## Interpretation

- **Whole-profile comparisons, not controlled KEM microbenchmarks:** Classic uses secp384r1; Hybrid and PQC-auth use X25519MLKEM768. Other certificate properties differ between Hybrid and PQC-auth.
- **High CPU occupancy:** the server was around 96% busy in all three profiles. Changing load/concurrency could change the ranking.
- **Two distinct latency metrics:** HTTP percentiles describe client-observed HTTP requests; eBPF data summarize duration of an observed `SSL_do_handshake()` *call*, not necessarily a full TLS negotiation or cryptographic CPU time.
- **Histogram estimates:** eBPF p50/p95/p99 were derived upstream via Prometheus histogram quantile interpolation. A mean of three per-run percentiles is not a pooled percentile.
- **Small sample:** three runs/profile. Standard-deviation error bars are not confidence intervals.
- **CPU efficiency:** calculated as (busy fraction × 4 vCPU × 120 seconds × 1000) / recorded full handshakes; includes all server CPU work and is not isolated cryptographic cost.

The older intermediate CSV's `cpu_percent` used broader 130-second extraction windows. The final figures use exact 120-second `cpu-120s.csv` values. Never mix the two.

This is a separate October campaign; it must not be pooled with the repository's November 4 HTTPS stability campaign.
