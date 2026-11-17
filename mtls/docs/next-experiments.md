# Next mTLS experiments for FOSDEM 2027

## First: source/configuration verification (required before new public claims)

Collect and review (after sanitization) the Apache VirtualHost declarations, explicit TLS group restrictions, certificate chains, certificate subject/issuer/algorithm/key usage/EKU, `wrk-mtls` build flags and patch, eBPF script, exporter and Prometheus queries. Run positive tests (`openssl s_client`, `curl --cert --key --cacert`) and negative tests (missing/expired/wrong-CA client cert, wrong server hostname, invalid CA trust), checking both TLS outcomes and HTTP access logs. Verify exactly what the `full/resumed` counters mean and how server-side `SSL_do_handshake()` returns are counted.

## Experiment A — marginal hybrid KEM effect (highest priority)

Add **ECDSA P-384 server/client cert + X25519** using the *same* certificate material, trust chain, HTTP payload, TLS version/cipher, Apache worker configuration and host resources as the existing ECDSA P-384 + `X25519MLKEM768` hybrid. Then pair and randomize runs. Keep Classic `secp384r1` in figures as a third baseline. This controls better for classical vs hybrid key exchange; do not change signature algorithms at the same time.

## Experiment B — authentication cost

Hold `X25519MLKEM768` constant, compare ECDSA P-384 and ML-DSA-65 authentication with both client and server certificates. If possible add *server-only* and *client-only* variations to separate costs; otherwise explicitly label it as a two-ended authentication comparison.

## Experiment C — different load profiles

At least 2, 10, 25 and 50 concurrent connections, 120 seconds each, five or more repetitions per profile per level, warm-up/cool-down, randomized or Latin-square profile order and a record of timestamp/CPU frequency/process counters. This distinguishes low-load response from near-CPU saturation. Preserve the existing nine runs as a different campaign; do not overwrite them.

## Experiment D — handshake bytes and CPU profiles (optional)

Capture handshake traffic in an isolated lab and measure connection bytes/packet count/fragmentation, particularly certificate chain and CertificateVerify differences. Optionally use `perf` (and versioned symbol maps) to compare cryptographic CPU samples. Report TLS record sizes separately from certificate file sizes.

## Reporting recommendations

Publish run-level CSV, honest uncertainty (sample SD and optionally confidence interval with more repeats), query/trace code, exact environment versions, positive/negative TLS evidence and stdout/stderr from validation. Include p50/p95/p99 for HTTP latency and for eBPF calls separately. Do not interpret the latter as pure cryptographic time or full end-to-end TLS handshake duration.
