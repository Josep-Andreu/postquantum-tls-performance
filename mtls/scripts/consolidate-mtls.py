#!/usr/bin/env python3
import csv
from pathlib import Path

base = Path(__file__).resolve().parents[1]
data = base / "data"

with (data / "round1.csv").open() as f:
    round1 = list(csv.DictReader(f))

with (data / "rounds2-3.csv").open() as f:
    extra = list(csv.DictReader(f))

assert len(round1) == 3
assert len(extra) == 6

rows = []

for round_number, group in [
    (1, round1),
    (2, extra[:3]),
    (3, extra[3:])
]:
    assert {r["profile"] for r in group} == {
        "mtls-classic", "mtls-hybrid", "mtls-pqc"
    }

    for r in group:
        profile = r["profile"]

        logfile = (
            f"{profile}.log" if round_number == 1
            else f"round{round_number}-{profile}.log"
        )

        assert (data / logfile).exists(), logfile

        rows.append({
            "round": round_number,
            "profile": profile,
            "logfile": logfile,
            "handshakes": r["handshakes"],
            "mean_ms": r["mean_ms"],
            "p50_ms": r["p50_ms"],
            "p95_ms": r["p95_ms"],
            "p99_ms": r["p99_ms"],
        })

output = base / "results" / "mtls-consolidated.csv"

with output.open("w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)

print(f"Created: {output}")
print(f"Runs: {len(rows)}")
