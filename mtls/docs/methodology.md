# mTLS campaign: protocol, design and limitations

## Setup and controlled parameters

Experimental stack: RHEL 9.8, Apache HTTP Server 2.4.62 with OpenSSL 3.5.x, TLS 1.3. Server: 4 virtual CPUs; client: 8 virtual CPUs. The benchmark used the authenticated wrk fork with 8 threads, 50 concurrent connections and 120 seconds per run. Each of the four profiles was executed five times in each of two observational conditions. Four profiles × five rounds × ON/OFF gives 40 runs total.

The runner randomized profile order within each round using a recorded fixed seed. These are repeated measures, not 40 independent physical hosts or microbenchmarks. The paired comparison assumes round labels capture comparable experimental conditions; results were not simultaneous and sequencing could still confound them.

All benchmarked TLS sessions were fresh (`Connection: close` and reported `resumed=0`). Different connections per request made the study particularly sensitive to handshake performance. HTTP target was `/`, known to return HTTP 200, not a missing benchmark resource. Both sides validated certificates in the new verified-wrk implementation.

## Cryptographic validity

- Client verifies the server chain using the matching CA trust file and verifies the expected hostname.
- Server requires and verifies the client's certificate.
- No-client-certificate, unauthorized-client-CA and wrong-server-CA negative tests were performed in the lab; acceptance/failure evidence is not included in public raw log form.
- Negotiated protocol/group/cipher were read from TLS diagnostics; resumed sessions were rejected as invalid for this benchmark.
- The custom wrk fork was manually validated for `SSL_VERIFY_PEER`, CA bundle loading and `SSL_set1_host()`; the legacy binary used in the October experiment was not equivalent.

A correct diagnostic string or nonzero handshake count alone does **not** cryptographically prove peer validation. Reproducers should repeat negative tests with controlled trust roots and compare the custom wrk source.

## Acquisition, dataset and calculations

All data for the main results is in [../data/results.csv](../data/results.csv), one row per profile, mode and round. The key fields are `mode`, `round`, `profile`, `rps`, `http_requests`, `tls_full`, `tls_resumed`, `latency_mean_ms`, `cpu_busy_pct`, `ebpf_completed`, `ebpf_full_count`, `ebpf_parse_errors`, `ebpf_full_mean_ms` and `wrk_exit`.

In observer-ON runs, the independent successful-event counter and the histogram count were each compared against wrk's TLS handshake count by per-run deltas. All 20 ON runs matched, and parser error deltas were zero. The network layer may have completed more TLS connections than successful HTTP responses near the test's abrupt end; this is expected.

For each profile, the figures show means and sample SD of five run-level values (not sample-level standard deviations over hundreds of thousands of connections). Figure 07 shows a two-sided t-based 95% confidence interval for the five paired throughput differences; no broader population inference is warranted from five runs. Figure 09 uses **pooled histogram bucket quantiles**, with interpolation and without per-run SD or CI.

A 99.5% average system-wide CPU busy value does not imply Apache consumed 99.5% of server CPU; it includes all tasks. The benchmark did not isolate ML-KEM or ML-DSA operations, CPU cycles, network bandwidth or distinct components of certificate-chain validation.

## Measurement boundaries and comparability

- Main **performance** results are from observer OFF.
- TLS server-side elapsed and percentile distributions are from observer ON.
- OFF to ON relative throughput changes include eBPF, Python parsing, polling and exporter activity; they do not quantify probe-only CPU cost.
- wrk's `Latency` is HTTP request latency, not client TLS setup. Do not add it to eBPF server-observed elapsed.
- eBPF v3 elapsed runs between the first and last `SSL_do_handshake()` probe for an SSL object. It excludes earlier TCP setup and may include scheduling gaps. The older eBPF metric represented only the successful final library call.
- Comparing Hybrid (X25519MLKEM768 + ECDSA) with X25519 (X25519 + ECDSA) controls authentication. Comparing the PQC-authentication profile with Hybrid changes authentication keys/certification context and therefore cannot isolate one algorithm.

## Data availability and privacy

The sanitized 40-row CSV and figure scripts are public; raw logs are not. Logs can include internal hostnames and local credential filenames and remain on the private lab hosts. Do not commit TLS private keys, PATs, hostnames, CA bundles, private IPs or unredacted configs. The pooled p50/p90/p95/p99 image derives from validated cumulative histogram buckets; to reproduce exactly, preserve the associated bucket snapshot or the `ebpf_percentiles_pooled.csv` generated alongside the plot. **The ordinary results.csv does not contain those percentiles.**

The main server-authenticated HTTPS study is a separate experiment preserved in the repository root.
