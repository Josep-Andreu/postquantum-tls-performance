#!/usr/bin/env python3
"""Offline consistency checks for the published 40-run mTLS experiment."""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILES = {"mtls-classic", "mtls-x25519", "mtls-hybrid", "mtls-pqc"}
EXPECTED = {(m, r, p) for m in ("off", "on") for r in range(1, 6) for p in PROFILES}

def main():
    with (ROOT / "data" / "results.csv").open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 40, f"expected 40 rows, got {len(rows)}"
    keys = {(x["mode"], int(x["round"]), x["profile"]) for x in rows}
    assert keys == EXPECTED and len(keys) == len(rows), "missing/duplicate run keys"
    for row in rows:
        assert int(row["wrk_exit"]) == 0
        assert int(row["tls_resumed"]) == 0
        assert float(row["rps"]) > 0
        assert int(row["tls_full"]) > 0
        assert 0 <= int(row["http_requests"]) <= int(row["tls_full"])
        assert float(row["latency_mean_ms"]) > 0
        assert 0 <= float(row["cpu_busy_pct"]) <= 100
        if row["mode"] == "on":
            assert int(row["ebpf_completed"]) == int(row["tls_full"])
            assert int(row["ebpf_full_count"]) == int(row["tls_full"])
            assert int(row["ebpf_parse_errors"]) == 0
            assert float(row["ebpf_full_mean_ms"]) > 0
        else:
            for field in ("ebpf_completed", "ebpf_full_count",
                          "ebpf_parse_errors", "ebpf_full_mean_ms"):
                assert not row[field], f"unexpected OFF field: {field}"
    print("PASS: 40 distinct runs; 4 profiles × 5 rounds × 2 modes")
    print("PASS: all wrk exits 0, no resumed sessions")
    print("PASS: ON handshakes and full histogram counts match wrk; parser errors 0")
    print("Note: CSV cannot by itself validate cryptographic peer verification.")

if __name__ == "__main__":
    main()
