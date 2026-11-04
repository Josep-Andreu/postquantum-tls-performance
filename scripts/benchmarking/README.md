# TLS Benchmark Orchestration

This directory contains `run-round.sh`, the script used to automate the classical and post-quantum TLS performance benchmarks described in the accompanying Red Hat Developer article.

The script executes five TLS profiles in a predefined order that varies between rounds, helping reduce systematic time-order bias.

## Prerequisites

The script must be executed on the load-generation client and requires:

- A modified build of `wrk` linked against OpenSSL 3.5 or later, with the changes described in the [wrk documentation](wrk/README.md).
- The `close.lua` script in the same directory as the `wrk` executable.
- OpenSSL client configuration files for ML-DSA-65 and ML-DSA-87/ML-KEM-1024.
- SSH access to the Apache web server, with permission to update `/run/pqc-observability/profile` and restart `pqc-tls-exporter`.
- Five Apache TLS virtual hosts configured with the corresponding profiles and ports.

## TLS profiles

| Profile | Port | Cryptographic configuration |
|---|---:|---|
| `classic-a2` | 8443 | Classical ECDHE (P-384), ECDSA P-384 |
| `classic-c2` | 9443 | Classical ECDHE (P-521), ECDSA P-521 |
| `pqc-a1` | 10443 | Hybrid X25519MLKEM768, ML-DSA-65 |
| `pqc-b1` | 11443 | Hybrid X25519MLKEM768, ML-DSA-65 authentication with an SLH-DSA-signed certificate |
| `pqc-c1` | 12443 | ML-KEM-1024, ML-DSA-87 |

## Running the benchmarks

Configure the target server and local paths, then execute a round:

```bash
WEB=web.lab.example.com \
WRK=/usr/local/src/wrk \
./run-round.sh 1
```

The script also supports the environment variables `BASE`, `SSH_TARGET`, `OPENSSL_MLDSA65`, and `OPENSSL_MLDSA87_MLKEM1024` to override their default values.

To execute all five rounds:

```bash
for round in 1 2 3 4 5; do
    ./run-round.sh "$round"
done
```

Each round executes all five TLS profiles using identical workload parameters:

```text
8 threads | 50 connections | 120 seconds | HTTP latency reporting
```

Before each benchmark, the script updates the active observability profile, restarts the TLS exporter, and waits 60 seconds for initialization.

The complete experiment consists of **25 executions and 50 minutes of active load generation**, excluding initialization delays.

## Results

By default, results are stored under:

```text
~/pqc-benchmark-results/120s-t8/
├── round1/
│   ├── classic-a2-wrk.log
│   ├── classic-c2-wrk.log
│   ├── pqc-a1-wrk.log
│   ├── pqc-b1-wrk.log
│   └── pqc-c1-wrk.log
├── round2/
├── round3/
├── round4/
└── round5/
```

Each log includes UTC start and end timestamps and the corresponding `wrk` output. Existing log files are not overwritten.

The script automates benchmark execution but does not install or configure the Apache server, OpenSSL, Prometheus, or the eBPF exporter. These components must be configured beforehand.

For the modified `wrk` build and OpenSSL client settings, see [wrk/README.md](wrk/README.md).
