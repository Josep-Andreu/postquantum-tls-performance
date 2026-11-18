#!/usr/bin/env python3
"""Add an eBPF p50/p90/p95/p99 figure to the existing mTLS campaign plots.

Run on the benchmark client after the 40-run campaign. The script reads
results.csv and the current exporter histogram through SSH. It only produces
percentiles when the live cumulative histogram can be proven to match ALL
five ON runs for EACH of the four TLS profiles, including bucket counts and
weighted means. If the exporter restarted or unrelated traffic contaminated
its counters, it stops rather than publishing misleading values.

This uses *pooled histogram* quantiles with Prometheus-style linear bucket
interpolation, NOT per-run quantiles with standard deviation. No benchmark
is executed and no TLS configuration is modified. Outputs have no hostnames.
"""
import argparse
import csv
import math
import re
import statistics
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

PROFILES = ["mtls-classic", "mtls-x25519", "mtls-hybrid", "mtls-pqc"]
LABELS = ["Classic\nECDSA P-384", "X25519\nECDSA P-384",
          "Hybrid\nECDSA + ML-KEM", "PQC\nML-DSA-65"]
COLORS = ["#249BFA", "#45D6C4", "#B58CFF", "#FF624D"]
BG, FG, MUTED, GRID = "#0B111A", "#F5F7FA", "#A0AEC0", "#293746"
QUANTILES = [0.50, 0.90, 0.95, 0.99]
METRIC_PREFIX = "tls_handshake_full_elapsed_seconds_"


def read_campaign(csv_file):
    by_profile = defaultdict(list)
    with csv_file.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fields = {"mode", "profile", "round", "ebpf_full_count",
                  "ebpf_full_mean_ms", "ebpf_completed", "ebpf_parse_errors",
                  "tls_full", "wrk_exit", "tls_resumed"}
        if not reader.fieldnames or not fields.issubset(reader.fieldnames):
            raise ValueError("The CSV lacks required mTLS campaign columns")
        for row in reader:
            if row["mode"].lower() == "on":
                if row["profile"] not in PROFILES:
                    raise ValueError("Unexpected profile in ON campaign")
                if (int(row["wrk_exit"]) != 0 or int(row["tls_resumed"]) != 0
                    or int(row["ebpf_parse_errors"]) != 0
                    or int(row["ebpf_full_count"]) != int(row["tls_full"])
                    or int(row["ebpf_completed"]) != int(row["tls_full"])):
                    raise ValueError("Incomplete or invalid ON campaign row")
                by_profile[row["profile"]].append(row)
    expected = {}
    for p in PROFILES:
        rows = by_profile[p]
        if len(rows) != 5 or {int(x["round"]) for x in rows} != {1, 2, 3, 4, 5}:
            raise ValueError(f"Expected exactly 5 validated ON rounds for {p}")
        n = sum(int(r["ebpf_full_count"]) for r in rows)
        weighted_mean_ms = sum(int(r["ebpf_full_count"]) *
                               float(r["ebpf_full_mean_ms"]) for r in rows) / n
        expected[p] = (n, weighted_mean_ms)
    return expected


def get_metrics(args):
    if args.metrics_file:
        return args.metrics_file.read_text(encoding="utf-8")
    if not args.web_host:
        raise ValueError("Specify --web-host (or --metrics-file from the exporter)")
    command = ["ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
               "-o", "ServerAliveInterval=20", f"root@{args.web_host}",
               "curl -fsS --max-time 12 http://127.0.0.1:9101/metrics"]
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=35)
    if result.returncode != 0:
        raise RuntimeError("Could not retrieve exporter metrics through SSH; "
                           "check that the exporter is running and SSH works")
    return result.stdout


def parse_metrics(metrics_text):
    by_profile = defaultdict(lambda: {"buckets": {}})
    for line in metrics_text.splitlines():
        if not line.startswith(METRIC_PREFIX):
            continue
        match = re.match(r'^(tls_handshake_full_elapsed_seconds_(?:bucket|count|sum))'
                         r'(\{([^}]*)\})?\s+([-+]?\S+)', line)
        if not match:
            continue
        name, _, labels_str, val_str = match.groups()
        labels = dict(re.findall(r'(\w+)="([^"]*)"', labels_str or ""))
        profile = labels.get("profile")
        if profile not in PROFILES:
            continue
        try:
            value = float(val_str)
            if name.endswith("_bucket"):
                if "le" not in labels:
                    continue
                le = float(labels["le"].replace("+Inf", "inf"))
                by_profile[profile]["buckets"][le] = value
            elif name.endswith("_count"):
                by_profile[profile]["count"] = value
            elif name.endswith("_sum"):
                by_profile[profile]["sum"] = value
        except (ValueError, OverflowError):
            continue
    return by_profile


def check_histograms(expected, observed):
    for profile, (n, mean_ms) in expected.items():
        v = observed.get(profile, {})
        if "count" not in v or "sum" not in v or not v.get("buckets"):
            raise ValueError(f"Missing histogram for {profile} in exporter metrics")
        count = v["count"]
        if not count.is_integer() or int(count) != n:
            raise ValueError(f"Histogram for {profile} contains {count:g} handshakes; "
                             f"campaign contains {n}. Cannot attribute it safely "
                             "to this campaign. Do not graph these percentiles.")
        actual_mean_ms = 1000.0 * v["sum"] / count
        if abs(actual_mean_ms - mean_ms) > 0.005:
            raise ValueError(f"Histogram mean for {profile} differs from the "
                             "campaign mean; likely a counter reset or contamination")
        buckets = sorted(v["buckets"].items())
        if not math.isinf(buckets[-1][0]) or buckets[-1][1] != n:
            raise ValueError(f"Incomplete or inconsistent +Inf bucket for {profile}")
        previous = 0
        for upper, cumulative in buckets:
            if not cumulative.is_integer() or cumulative < previous or cumulative > n:
                raise ValueError(f"Non-monotonic histogram buckets for {profile}")
            previous = cumulative
    return True


def quantile_ms(bucket_dict, q):
    pairs = sorted(bucket_dict.items())
    total = pairs[-1][1]
    rank = q * total
    lo, count_lo = 0.0, 0.0
    for hi, count_hi in pairs:
        if count_hi >= rank:
            if math.isinf(hi):
                raise ValueError("p99 lies in +Inf bucket: histogram resolution insufficient")
            if count_hi == count_lo:
                return 1000.0 * hi
            return 1000.0 * (lo + (hi - lo) * (rank - count_lo) / (count_hi - count_lo))
        lo, count_lo = hi, count_hi
    raise ValueError("Invalid histogram")


def plot_percentiles(quantiles, expected, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 12,
        "text.color": FG, "axes.labelcolor": FG,
        "xtick.color": FG, "ytick.color": MUTED,
        "axes.edgecolor": GRID, "axes.facecolor": BG,
        "figure.facecolor": BG, "savefig.facecolor": BG,
        "axes.titleweight": "bold", "axes.titlesize": 21,
        "grid.color": GRID, "grid.alpha": 0.65,
        "pdf.fonttype": 42, "svg.fonttype": "none"
    })
    fig, ax = plt.subplots(figsize=(16, 9))
    fig.subplots_adjust(left=0.09, right=0.96, top=0.73, bottom=0.20)
    fig.text(0.09, 0.92, "mTLS handshake latency distribution", fontsize=25,
             fontweight="bold", color=FG)
    fig.text(0.09, 0.865,
             "eBPF v3 full elapsed histogram quantiles | 5 pooled runs/profile | eBPF ON",
             fontsize=13, color=MUTED)
    ax.set_ylabel("Observed handshake elapsed (ms)", fontsize=13, labelpad=15)
    ax.grid(axis="y", linestyle="--"); ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(axis="both", length=0, pad=9)
    x = np.arange(len(PROFILES))
    width = 0.18
    alphas = [0.36, 0.56, 0.76, 1.0]
    for j, (q, alpha) in enumerate(zip(QUANTILES, alphas)):
        v = [quantiles[p][q] for p in PROFILES]
        ax.bar(x + (j-1.5)*width, v, width=width,
               color=COLORS, alpha=alpha, label=f"p{round(100*q)}")
    ax.set_xticks(x, LABELS)
    max_value = max(v for p in PROFILES for v in quantiles[p].values())
    ax.set_ylim(0, max_value * 1.28)
    ax.legend(loc="upper right", frameon=False, labelcolor=FG, ncol=4)
    fig.text(0.09, 0.095,
             "Quantiles interpolated from pooled Prometheus buckets | "
             "No per-run SD/CI | 5 x 120 s runs/profile",
             fontsize=10.5, color=MUTED)
    out.mkdir(parents=True, exist_ok=True)
    name = "09-mtls-ebpf-percentiles-dark"
    for suffix in ("png", "svg", "pdf"):
        fig.savefig(out / f"{name}.{suffix}", dpi=300, facecolor=BG)
    plt.close(fig)
    path = out / "ebpf_percentiles_pooled.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["profile", "handshakes", "p50_ms", "p90_ms", "p95_ms", "p99_ms",
                         "source", "aggregation"])
        for p in PROFILES:
            writer.writerow([p, expected[p][0]] +
                            [f"{quantiles[p][q]:.4f}" for q in QUANTILES] +
                            ["tls_handshake_full_elapsed_seconds_bucket", "pooled_ON_5_runs"])
    return name, path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--web-host", default="", help="SSH server for the live exporter")
    parser.add_argument("--metrics-file", type=Path, help="Offline exporter metrics snapshot")
    parser.add_argument("--out", type=Path, help="Default: CSV directory / figures / dark")
    args = parser.parse_args()
    try:
        expected = read_campaign(args.csv)
        observed = parse_metrics(get_metrics(args))
        check_histograms(expected, observed)
        qs = {p: {q: quantile_ms(observed[p]["buckets"], q) for q in QUANTILES}
              for p in PROFILES}
        out = args.out or args.csv.parent / "figures" / "dark"
        name, csv_path = plot_percentiles(qs, expected, out)
        for p in PROFILES:
            print(f"{p:14} | n={expected[p][0]:7} | " +
                  " | ".join(f"p{round(q*100)}={qs[p][q]:.2f} ms" for q in QUANTILES))
        print("PASS: Live histogram totals and means match all 20 instrumented runs")
        print("Created:", out / f"{name}.png", "(+ SVG and PDF)")
        print("Summary:", csv_path)
    except (ValueError, OSError, RuntimeError, subprocess.TimeoutExpired) as e:
        print("CANNOT RECOVER VALID HISTOGRAMS:", e, file=sys.stderr)
        print("No percentiles were invented. If the exporter was restarted, "
              "historical Prometheus samples or a new ON-only run would be needed.",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())