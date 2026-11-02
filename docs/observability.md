# TLS observability with eBPF, Prometheus, and Grafana

This document describes the instrumentation used for the **Post-Quantum TLS: Beyond the Handshake** experiments. It covers Apache HTTP Server with OpenSSL, `bpftrace` uprobes, a Python Prometheus exporter, Apache `mod_status`, node-exporter, and Grafana.

> **Scope:** This is an experimental observability stack, not a hardened production deployment. All hostnames below are illustrative and use the reserved `lab.example.com` domain.

## 1. Architecture

```text
TLS load generator (client.lab.example.com)
                  |
                  v
Apache HTTP Server + OpenSSL (web.lab.example.com)
   |                               |
   | SSL_do_handshake()            | /server-status?auto (loopback)
   v                               v
bpftrace uprobe/uretprobe     Apache mod_status
   |                               |
   +----------> Python TLS exporter <----------+
                      | :9101 /metrics
                      v
            Prometheus (observability.lab.example.com)
                      ^
                      | :9100 /metrics
                 node-exporter on web
                      |
                      v
                    Grafana
```

Prometheus scrapes the custom TLS exporter on port **9101** and node-exporter on port **9100**, using a **1-second** scrape interval and **900 ms** scrape timeout. Grafana visualizes the resulting time series.

## 2. Repository files

| File | Purpose |
| --- | --- |
| `scripts/observability/bpftrace/tls_handshake.bt` | Traces calls to OpenSSL's `SSL_do_handshake()` in Apache processes |
| `scripts/observability/exporter/tls_exporter.py` | Parses bpftrace output and exports Prometheus metrics; polls Apache `mod_status` |
| `scripts/observability/exporter/requirements.txt` | Python dependency (`prometheus-client`) |
| `scripts/observability/systemd/pqc-tls-exporter.service` | systemd unit for the exporter |
| `scripts/observability/prometheus/prometheus.yml.example` | Example Prometheus scrape configuration |
| `scripts/observability/grafana/tls-pqc-observatory.json` | Grafana dashboard JSON |

## 3. How the eBPF tracing works

The `bpftrace` script attaches an **uprobe** to `/usr/lib64/libssl.so.3:SSL_do_handshake` and a matching **uretprobe**. It filters events to processes whose command name is `httpd`.

On function entry, it records a timestamp and the SSL pointer, indexed by thread. On return, it calculates elapsed nanoseconds and prints an event containing the PID, TID, duration, and OpenSSL return value. A process-exit tracepoint cleans up outstanding state. The exporter consumes lines in this format:

```text
HANDSHAKE pid=1234 tid=1234 duration_ns=7600000 result=1
```

This is an illustrative event, not a recorded benchmark sample. A return value of `1` is classified as `completed`; other return values are classified as `incomplete`. Only completed calls contribute to the duration histogram.

**Measurement boundary:** These measurements are durations of individual `SSL_do_handshake()` calls. In nonblocking TLS, a complete handshake may require several calls. Consequently, neither the histogram nor the `completed` counter should be interpreted unconditionally as end-to-end handshake latency or a unique count of TLS connections. The script does not directly capture negotiated cipher suites, groups, or certificate algorithms.

## 4. Installation on the Apache host

The implementation was deployed with the following fixed paths:

```text
/root/pqc-observability/
  bpftrace/tls_handshake.bt
  exporter/tls_exporter.py
  venv/
/run/pqc-observability/profile
```

The example below preserves those paths rather than changing the working exporter. Run it on the Apache host as an administrator. Ensure that the system provides Apache with OpenSSL 3 (`/usr/lib64/libssl.so.3`), `bpftrace`, Python 3, `venv` support, and the tracing permissions needed for uprobes. Package names and available permissions depend on the RHEL installation and its security policy.

```bash
cd /root/postquantum-tls-performance

install -d -m 0755 /root/pqc-observability/bpftrace
install -d -m 0755 /root/pqc-observability/exporter
install -d -m 0755 /run/pqc-observability

install -m 0755 scripts/observability/bpftrace/tls_handshake.bt \
  /root/pqc-observability/bpftrace/tls_handshake.bt
install -m 0755 scripts/observability/exporter/tls_exporter.py \
  /root/pqc-observability/exporter/tls_exporter.py

python3 -m venv /root/pqc-observability/venv
/root/pqc-observability/venv/bin/python -m pip install \
  -r scripts/observability/exporter/requirements.txt

printf '%s\n' 'classic-a2' > /run/pqc-observability/profile

install -m 0644 scripts/observability/systemd/pqc-tls-exporter.service \
  /etc/systemd/system/pqc-tls-exporter.service
systemctl daemon-reload
systemctl enable --now pqc-tls-exporter.service
```

The directory under `/run` is ephemeral; recreate it and set the experiment profile after a reboot, **before running a benchmark**. For a persistent setup, add an appropriate `tmpfiles.d` rule or equivalent provisioning step. The profile file is read at event-processing time, not just when the exporter starts.

### Apache status endpoint

The exporter polls `http://127.0.0.1/server-status?auto` once per second with a **0.8-second** timeout. Apache must have `mod_status` enabled and permit this endpoint from loopback. Restrict access to localhost rather than exposing server status publicly. For example, adapt the Apache configuration to provide:

```apache
<Location "/server-status">
    SetHandler server-status
    Require local
</Location>
```

Verify locally:

```bash
curl -fsS http://127.0.0.1/server-status?auto
```

The exporter expects `Total Accesses`, `BusyWorkers`, `IdleWorkers`, `ReqPerSec`, and `BytesPerSec` fields.

## 5. Experimental profile labeling

The exporter reads `/run/pqc-observability/profile` and accepts the following profile names:

| Classical / PQ TLS profiles | Additional mTLS profiles |
| --- | --- |
| `classic-a2` | `mtls-classic` |
| `classic-c2` | `mtls-hybrid` |
| `pqc-a1` | `mtls-x25519` |
| `pqc-b1` | `mtls-pqc` |
| `pqc-c1` | |

For example, before starting a `pqc-b1` load test:

```bash
printf '%s\n' 'pqc-b1' > /run/pqc-observability/profile
cat /run/pqc-observability/profile
```

Missing or unrecognized values are labeled `unknown`. The label is **operator-supplied experimental context**: it is not obtained from the TLS connection itself. Run one profile at a time, account for in-flight handshakes when switching profiles, and document the test boundaries to avoid misleading attribution.

## 6. Prometheus metrics

The custom exporter serves `/metrics` on `0.0.0.0:9101`.

| Metric | Type | Interpretation |
| --- | --- | --- |
| `tls_handshake_calls_total{profile,result}` | Counter | Observed `SSL_do_handshake()` returns, classified `completed` or `incomplete` |
| `tls_handshakes_completed_total{profile}` | Counter | Calls returning `1`, not necessarily unique connections |
| `tls_handshake_duration_seconds{profile}` | Histogram | Duration of calls returning `1`; provides `_bucket`, `_sum`, and `_count` series |
| `tls_observer_last_event_timestamp_seconds` | Gauge | Time of the last parsed TLS event |
| `tls_observer_up` | Gauge | Whether the exporter considers its bpftrace subprocess running |
| `tls_observer_parse_errors_total` | Counter | Unexpected or malformed observer output |
| `tls_observer_restarts_total` | Counter | Number of observer launches within the exporter process lifetime |
| `tls_observer_profile_info{profile}` | Gauge | Selected profile (`1` for current, `0` for previously selected profiles) |
| `apache_status_up` | Gauge | Apache status collection success (`1`) or failure (`0`) |
| `apache_busy_workers` / `apache_idle_workers` | Gauge | Apache worker counts |
| `apache_requests_per_second` | Gauge | Rate reported by Apache `mod_status` |
| `apache_bytes_per_second` | Gauge | Throughput reported by Apache `mod_status` |
| `apache_accesses_total` | Counter | Apache total accesses, as exposed by the implementation |

The Apache accesses metric is populated directly from the `Total Accesses` value returned by `mod_status`, using the Prometheus client's internal counter value. Treat it as an experimental metric and validate behavior across Apache restarts before using it for rate calculations.

Check the exporter locally:

```bash
systemctl status pqc-tls-exporter.service
journalctl -u pqc-tls-exporter.service -n 50 --no-pager
curl -fsS http://127.0.0.1:9101/metrics | grep -E \
  '^(tls_observer_up|apache_status_up|tls_handshake_calls_total)'
```

The histogram and per-profile counters may not appear until events have been observed.

## 7. Prometheus configuration

The repository provides `scripts/observability/prometheus/prometheus.yml.example`. Its scrape jobs are named `pqc-tls-ebpf` and `pqc-web-node`:

```yaml
global:
  scrape_interval: 1s
  evaluation_interval: 1s
  scrape_timeout: 900ms

scrape_configs:
  - job_name: "pqc-tls-ebpf"
    static_configs:
      - targets: ["web.lab.example.com:9101"]
        labels:
          environment: "pqc-lab"
          service: "apache"
          observer: "ebpf"

  - job_name: "pqc-web-node"
    static_configs:
      - targets: ["web.lab.example.com:9100"]
        labels:
          environment: "pqc-lab"
          role: "web-server"
          experiment: "tls-pqc"
```

This is a **standalone example**. Merge these jobs into an existing Prometheus configuration if other scrape jobs already exist. The node-exporter on port 9100 must be installed and running separately; it is not provided by this repository. Configure name resolution for `web.lab.example.com` in your own lab, or replace it with your own permitted test hostname.

In Prometheus, check:

```promql
up{job="pqc-tls-ebpf"}
up{job="pqc-web-node"}
```

Both should be `1` when the targets are reachable and successfully scraped.

## 8. Example PromQL queries

**Completed OpenSSL calls per second:**

```promql
sum by (profile) (rate(tls_handshakes_completed_total[1m]))
```

**Mean duration of successful calls:**

```promql
sum by (profile) (rate(tls_handshake_duration_seconds_sum[1m]))
/
sum by (profile) (rate(tls_handshake_duration_seconds_count[1m]))
```

**Estimated 99th percentile from histogram buckets:**

```promql
histogram_quantile(
  0.99,
  sum by (le, profile) (rate(tls_handshake_duration_seconds_bucket[1m]))
)
```

**Share of observed calls returning success:**

```promql
sum by (profile) (rate(tls_handshake_calls_total{result="completed"}[1m]))
/
sum by (profile) (rate(tls_handshake_calls_total[1m]))
```

This last ratio is **not** a TLS connection success rate. OpenSSL can return non-success values for nonblocking handshakes that subsequently complete.

## 9. Grafana dashboard

Import `scripts/observability/grafana/tls-pqc-observatory.json` through Grafana's dashboard import interface, then select the appropriate Prometheus data source. The dashboard, **TLS Post-Quantum Performance Observatory**, combines observer health, OpenSSL-call duration distributions, Apache request activity, and host-level signals such as CPU and networking (from node-exporter).

Review the imported panels' data-source bindings: a dashboard exported from another Grafana instance may contain data-source UIDs that do not exist in the target environment. The original experimental dashboard also used a different Prometheus UID in one Apache request-rate panel; check and remap that panel if necessary.

Use aligned time windows and clearly marked benchmark runs when comparing classical and post-quantum profiles.

## 10. Operational and methodological limitations

1. **Call timing versus handshake timing.** A `SSL_do_handshake()` call is not necessarily a complete TLS handshake; the measured interval does not capture all client-observed network and application effects.
2. **Profile attribution.** The profile is read from a local text file. It does not prove which algorithms were negotiated by each connection.
3. **Return-value semantics.** `result != 1` is labeled `incomplete`, not conclusively failed. Nonblocking TLS can require retries.
4. **Tracing scope.** The bpftrace script filters by the `httpd` process name and the configured OpenSSL shared-library path. Other TLS implementations and processes are outside its scope.
5. **Process and restart behavior.** The exporter launches bpftrace as a subprocess. Its systemd unit uses `Restart=on-failure`; the Python exporter does not implement a separate internal retry loop for observer exits.
6. **Monitoring overhead.** Uprobes, Python parsing, one-second scrapes, and Apache status polling may influence results. Keep instrumentation consistent between comparison runs and report its overhead when possible.
7. **Metrics access.** The exporter binds to `0.0.0.0:9101` without authentication in the supplied code. Limit inbound access to the Prometheus server with host/network firewall controls. Do not expose the endpoint to the public internet.
8. **Ephemeral runtime state.** `/run/pqc-observability/profile` must be recreated after reboot. Missing state is reported as `unknown`.

## 11. Reproducibility checklist

Before each benchmark, verify that Apache and the exporter are running; the `mod_status` endpoint works; both Prometheus targets report `up=1`; the intended profile is written to the profile file; the exporter reports a running observer; and the dashboard panels use the correct Prometheus data source. Record the profile, test duration, concurrency, server CPU utilization, and benchmark tool parameters alongside exported results.

For the complete benchmark methodology and results, see the repository README and the accompanying article.
