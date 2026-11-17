#!/usr/bin/env python3
"""Verify that the published mTLS run-level CSV is internally consistent.
This is *not* independent validation of TLS or eBPF implementation.
"""
import csv
from pathlib import Path
from collections import defaultdict
ROOT=Path(__file__).resolve().parents[1]
with (ROOT/"data/runs.csv").open(newline="") as f:
    rows=list(csv.DictReader(f))
assert len(rows)==9
profiles={"mtls-classic","mtls-hybrid","mtls-pqc"}
keys={(int(r["round"]),r["profile"]) for r in rows}
assert keys=={(n,p) for n in (1,2,3) for p in profiles}
assert len(keys)==9
for r in rows:
    full=int(r["handshakes_full"])
    req=int(r["wrk_http_requests"])
    assert full>0 and 0<=full-req<=100
    assert int(r["handshakes_resumed"])==0
    assert float(r["wrk_requests_per_sec"])>0
    assert 0<float(r["ebpf_p50_ms"])<=float(r["ebpf_p95_ms"])<=float(r["ebpf_p99_ms"])
    assert abs(sum(float(r[c]) for c in ("cpu_user_pct","cpu_system_pct","cpu_irq_pct"))-float(r["cpu_busy_pct"]))<0.011
total=sum(int(r["handshakes_full"]) for r in rows)
assert total==1108144
print(f"PASS: {len(rows)} recorded runs, {len(profiles)} profiles, {total:,} recorded full handshakes, zero recorded resumptions.")
print("Scope: internal CSV consistency; raw TLS/eBPF sources not independently validated.")
