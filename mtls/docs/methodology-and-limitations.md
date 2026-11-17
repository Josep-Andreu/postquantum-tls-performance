# Measurement methodology and evidence boundaries

## What is directly contained in the historical archive

- Nine `wrk` log files, each labelled with the TLS 1.3 negotiated group and server public-key algorithm, plus a line stating that a client certificate file was loaded.
- Three rounds × three profiles; 120 seconds, eight `wrk` threads, 50 client connections.
- A client instrumentation line for each run, reporting `full=N resumed=0 total=N`.
- Three-run, per-profile eBPF-derived metrics (average and histogram-estimated p50/p95/p99) provided as CSV values. The original Prometheus range-vector queries and histogram time series were not included.
- CPU breakdown values from the exact 120-second windows in `data/cpu-120s.csv`. Their underlying Prometheus series and queries are not included.
- Eight figures and the original analysis scripts, with paths adapted for portability.

## What the audit validates

`python mtls/scripts/verify-mtls.py` confirms profile/round uniqueness, recorded protocol/group/public-key labels, absence of **reported** resumption, recorded client-side handshake totals matching the consolidated CSV, 120-second load labels, CPU component consistency and presence of eight PNG figures. It does not make a network connection.

**Important distinction:** the 9 identical handshake numbers seen in the client logs and `mtls-consolidated.csv` are not two independently preserved counter traces. Without the Prometheus source queries/raw measurements, this archive cannot independently demonstrate the claimed client ↔ eBPF counter agreement. That claim is described in the lab notes and should be confirmed from the original observability machine before being presented as independently audited evidence.

## What is *not* validated with this archive

- `wrk`'s C changes: client-certificate selection, enforcement of CA validation and `SSL_set1_host()`, error handling, full/resumed counters and full handshake semantics.
- Apache VirtualHost directives, `SSLVerifyClient require`, accepted CAs, verified client certificate chain, Extended Key Usage and rejection of missing/invalid client credentials.
- eBPF probe implementation and the exact definition of the successful `SSL_do_handshake()` completion counter. A nonblocking handshake may require multiple library calls; counting return events is not automatically equivalent to counting entire completed TLS handshakes.
- Prometheus raw histogram buckets, range windows, query expressions or exact wall-clock timestamps for each run.
- Source of `data/cpu-120s.csv` and exact host/system resource configuration beyond the lab notes.
- TLS record-level packet sizes or isolated cryptographic CPU cycles.

## Consolidation order assumption

`data/rounds2-3.csv` does not contain an explicit round-number field. The original `consolidate-mtls.py` assigns the first three rows to round 2 and the following three to round 3. This matches the attached historical logs and the preserved consolidated CSV, but a more robust future extraction should retain a unique run ID and timestamps in every row. Do not reorder the intermediate CSV before reconsolidation.

## CPU denominator and historical fields

The old `cpu_percent` and `cpu_s_per_1000` columns in `data/round1.csv` and `data/rounds2-3.csv` were reported in the original intermediate extraction over expanded 130-second windows. The final 2026 report uses `data/cpu-120s.csv` instead, yielding roughly 96% CPU across profiles. The plotting script's final CPU figures are based on this latter file and calculate:

`CPU-s / 1,000 recorded full handshakes = (CPU_busy_fraction * 4 vCPU * 120 seconds * 1,000) / recorded_handshakes`.

This is a **system-wide** efficiency metric, not a measurement of CPU usage by cryptographic functions alone.

## Non-causal comparisons

Classic uses `secp384r1`, whereas Hybrid and PQC-authentication use `X25519MLKEM768`. Therefore, Hybrid versus Classic does **not** isolate the marginal effect of ML-KEM, and it cannot justify a broad claim that a PQ scheme beats a classical KEM. Hybrid versus PQC-authentication holds the key exchange group constant but changes both client and server authentication and the certificate properties.

With only three runs/profile, differences in p99 call latency require careful treatment. Percentiles from Prometheus histogram bucket interpolation are estimates, and averages of per-run quantiles are not equivalent to quantiles of a pooled sample. Report statistical uncertainty explicitly and avoid cross-campaign pooling with the earlier HTTPS benchmark.

## Publication and security

Historical logs in this directory have had the lab hostname and absolute root certificate paths replaced. No key material is included. Audit generated vector figures for inadvertent infrastructure labels before publishing further data, and redact shell histories, CA private keys, credentials, internal network ranges and actual client/host identities from any future added files.
