# Follow-up experiments for FOSDEM 2027

## Priority 1: validate the measurement path
Recover the complete Apache mTLS virtual-host configuration, relevant OpenSSL client/server certificate and trust-chain metadata, the custom `wrk-mtls` patch/build flags, eBPF instrumentation source, exporter and Prometheus queries. Verify `SSL_do_handshake()` counting (non-blocking callers can invoke this function multiple times per negotiated session), certificate verification, hostname verification and negative authentication cases.

## Priority 2: isolate the hybrid key-establishment change
Add **ECDSA P-384 server/client certificates + X25519** while keeping all other settings identical to the current ECDSA P-384 + X25519MLKEM768 profile: same actual certificates, trust chain, payload, TLS cipher, httpd worker configuration, number of CPUs and load parameters. Pair runs in randomized orders. Retain the existing secp384r1 baseline as a separate historical comparison.

## Priority 3: vary load and repeat
Use 2, 10, 25 and 50 connections with at least five repetitions per profile, fixed run duration, warm-up, stabilization interval, UTC timestamps, CPU frequency and counters. Plot throughput *and* client-observed p50/p99, not throughput alone.

## Optional
Inspect certificate sizes and handshake packets (`tcpdump` in an isolated lab); use `perf` to profile cryptographic hotspots and the relative cost of ML-DSA authentication. Keep server-only HTTPS and two-ended mTLS campaigns in distinct datasets.
