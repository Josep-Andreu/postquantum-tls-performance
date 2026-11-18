# mTLS eBPF observer: what is actually measured

## Probe evolution

The original observer timed one successful `SSL_do_handshake()` call and did not guarantee that multiple invocations on a nonblocking SSL object were covered. The later version tracks a first-seen invocation by (PID, SSL pointer), records a start time for the current thread invocation, and reports one successful `COMPLETE` event per SSL object; it also emits `CALL` for intermediate incomplete calls and `ABORT` for SSL objects freed without success.

An initial v3 implementation incorrectly compared two elapsed intervals derived from separate evaluations of bpftrace `nsecs`. Most events were dropped because a single-call total could be a few hundred nanoseconds smaller than the call duration. This was fixed by **capturing exactly one start timestamp and one end timestamp per call**; the corrected version is in [../scripts/observability/tls_handshake_v3.bt](../scripts/observability/tls_handshake_v3.bt).

Successful event example (durations in nanoseconds):

~~~text
COMPLETE pid=123 tid=456 call_ns=8000000 elapsed_ns=8100000 result=1
~~~

In single-invocation success, `call_ns == elapsed_ns`. With multiple calls, `elapsed_ns >= call_ns`. The exporter rejects negative values, non-success results and inconsistent intervals.

## Metric semantics

| Metric | Meaning |
|:--|:--|
| `tls_handshakes_completed_total` | successful, fully observed SSL objects |
| `tls_handshake_calls_total{result="completed"}` | successful final invocations |
| `tls_handshake_calls_total{result="incomplete"}` | non-success invocation returns |
| `tls_handshake_duration_seconds` | last successful invocation duration (legacy-compatible) |
| `tls_handshake_call_duration_seconds` | individual function-call duration histogram |
| `tls_handshake_elapsed_seconds` | legacy metric; final-call duration, **not** new full elapsed |
| `tls_handshake_full_elapsed_seconds` | first observed call to successful completion |

Apache `mod_status` was polled by the Python exporter. The server measured host CPU utilization from `/proc/stat` snapshots; this is host-level busy percentage, not isolated application CPU time.

## Correctness checks

The four-profile smoke test and X25519 load test passed: wrk successful handshake totals matched the exporter completed counter and full elapsed histogram sample count. Under the 40-run campaign all 20 instrumented runs matched with zero parser errors. The actual probe and exporter should be validated jointly after any restart or change, rather than assuming a syntactically valid probe guarantees accurate counts.

## Instrumentation overhead

The preliminary ON–OFF–OFF–ON X25519 pilot showed a ~9.1% throughput deficit with v2 versus ~6.0% with v3; those pilots were not identical or sufficiently randomized to establish a definitive improvement. In the main five-round, four-profile campaign the observer ON/OFF throughput reductions were 4.26% (Classic), 5.37% (X25519), 4.64% (Hybrid) and 5.91% (ML-DSA-65). Entire observer service ON/OFF, not the isolated eBPF probe, was the experimental contrast.

## Percentile estimation

The 09 figure was calculated from a validated pooled histogram of all five observer-ON runs per profile. This is a **bucket-interpolated quantile**, not a precise sample percentile and not an average of five independent p99s. Tail bins are wide and estimation error can be large. The histogram source should be archived with the figure where available. If the exporter restarts or unrelated TLS connections enter the sample window, cumulative current metrics are not a valid substitute.
