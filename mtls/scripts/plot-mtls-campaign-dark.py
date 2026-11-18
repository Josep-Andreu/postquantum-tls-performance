#!/usr/bin/env python3
"""Render the 2026 mTLS 4-profile campaign on the benchmark client.

Visual theme intentionally matches mtls/scripts/plot-mtls-dark.py in the
original, published mTLS study: same background, typeface, grid, layout,
profile colours, 16:9 dimensions, output DPI and PNG/PDF/SVG formats.

The four-profile campaign has an additional colour for X25519; existing
classic/hybrid/PQC colours remain unchanged. This script never connects to
hosts, touches the exporter, runs benchmarks, or publishes to GitHub.

Usage:
    python3 plot_mtls_campaign_dark.py
    python3 plot-mtls-campaign-dark.py --csv ./results.csv
"""

import argparse
import csv
import math
import statistics as stats
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# Exact styling adopted from the original mtls/scripts/plot-mtls-dark.py.
BG = "#0B111A"
FG = "#F5F7FA"
MUTED = "#A0AEC0"
GRID = "#293746"
CLASSIC = "#249BFA"  # original blue
HYBRID = "#B58CFF"  # original violet
PQC = "#FF624D"     # original coral
X25519 = "#45D6C4"  # newly assigned teal (4th profile)

PROFILES = ["mtls-classic", "mtls-x25519", "mtls-hybrid", "mtls-pqc"]
LABELS = ["Classic\nECDSA P-384", "X25519\nECDSA P-384",
          "Hybrid\nECDSA + ML-KEM", "PQC\nML-DSA-65"]
COLORS = [CLASSIC, X25519, HYBRID, PQC]
SHORT = {"mtls-classic": "Classic", "mtls-x25519": "X25519",
         "mtls-hybrid": "Hybrid", "mtls-pqc": "PQC"}
T_95_DF4 = 2.7764451051977987  # Student's t 95% two-sided, n=5

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 12,
    "text.color": FG,
    "axes.labelcolor": FG,
    "xtick.color": FG,
    "ytick.color": MUTED,
    "axes.edgecolor": GRID,
    "axes.facecolor": BG,
    "figure.facecolor": BG,
    "savefig.facecolor": BG,
    "axes.titleweight": "bold",
    "axes.titlesize": 21,
    "grid.color": GRID,
    "grid.alpha": 0.65,
    "pdf.fonttype": 42,
    "svg.fonttype": "none",
})


def make_figure(title, subtitle, ylabel):
    fig, ax = plt.subplots(figsize=(16, 9))
    fig.subplots_adjust(left=0.09, right=0.96, top=0.73, bottom=0.20)
    fig.text(0.09, 0.92, title, fontsize=25, fontweight="bold", color=FG)
    fig.text(0.09, 0.865, subtitle, fontsize=13, color=MUTED)
    ax.set_ylabel(ylabel, fontsize=13, labelpad=15)
    ax.grid(axis="y", linestyle="--")
    ax.set_axisbelow(True)
    for side in ["top", "right", "left"]:
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(axis="both", length=0, pad=9)
    return fig, ax


def footer(fig, message):
    fig.text(0.09, 0.095, message, fontsize=10.5, color=MUTED)


def save(fig, output_dir, name):
    for ext in ("png", "pdf", "svg"):
        fig.savefig(output_dir / f"{name}.{ext}", dpi=300, facecolor=BG)
    plt.close(fig)
    print(f"  Created {name}.png / .pdf / .svg", flush=True)


def latest_input():
    matches = list(Path("/root").glob("mtls-campaign-*/results.csv"))
    if not matches:
        raise ValueError("No campaign CSV found; provide --csv /path/to/results.csv")
    return max(matches, key=lambda p: p.stat().st_mtime)


def read_verified_csv(path):
    groups = defaultdict(dict)
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        needed = {"mode", "round", "profile", "rps", "http_requests",
                  "tls_full", "tls_resumed", "latency_mean_ms", "cpu_busy_pct",
                  "ebpf_completed", "ebpf_full_count", "ebpf_parse_errors",
                  "ebpf_full_mean_ms", "wrk_exit"}
        if not reader.fieldnames or not needed.issubset(reader.fieldnames):
            raise ValueError("Input is not the expected mtls_campaign.py results.csv")
        for row in reader:
            key = (row["mode"], row["profile"])
            if row["mode"] not in ("on", "off") or row["profile"] not in PROFILES:
                raise ValueError(f"Unknown mode/profile: {key}")
            r = int(row["round"])
            if r in groups[key]:
                raise ValueError(f"Duplicate mode/profile/round: {key} {r}")
            if int(row["wrk_exit"]) != 0 or int(row["tls_resumed"]) != 0:
                raise ValueError(f"Failed/unverified run: {key} {r}")
            if float(row["rps"]) <= 0 or int(row["tls_full"]) <= 0:
                raise ValueError(f"Empty workload: {key} {r}")
            if row["mode"] == "on":
                if (int(row["ebpf_completed"]) != int(row["tls_full"])
                        or int(row["ebpf_full_count"]) != int(row["tls_full"])
                        or int(row["ebpf_parse_errors"]) != 0):
                    raise ValueError(f"eBPF counter mismatch: {key} {r}")
            groups[key][r] = row
    expected_rounds = {1, 2, 3, 4, 5}
    for mode in ("off", "on"):
        for profile in PROFILES:
            present = set(groups[(mode, profile)])
            if present != expected_rounds:
                raise ValueError(f"Incomplete 5-round campaign: {mode} {profile} (found {sorted(present)})")
    if sum(len(v) for v in groups.values()) != 40:
        raise ValueError("Expected exactly 40 run rows")
    return groups


def values(groups, mode, profile, metric):
    return np.array([float(groups[(mode, profile)][r][metric]) for r in range(1, 6)])


def summary(groups, mode, metric):
    all_values = [values(groups, mode, p, metric) for p in PROFILES]
    means = np.array([stats.mean(a) for a in all_values])
    stds = np.array([stats.stdev(a) for a in all_values])
    return means, stds


def standard_bars(groups, out, mode, metric, title, subtitle, ylabel, filename,
                  formatter, upper=None, lower=0):
    x = np.arange(len(PROFILES))
    means, stds = summary(groups, mode, metric)
    fig, ax = make_figure(title, subtitle, ylabel)
    bars = ax.bar(x, means, width=0.62, color=COLORS, yerr=stds, capsize=5,
                  error_kw={"ecolor": FG, "elinewidth": 1.7, "capthick": 1.7})
    ax.set_xticks(x, LABELS)
    top = upper if upper is not None else max(means + stds) * 1.23
    ax.set_ylim(lower, top)
    margin = (top - lower) * 0.019
    for i, (bar, val, sd) in enumerate(zip(bars, means, stds)):
        ax.text(bar.get_x()+bar.get_width()/2, val + sd + margin,
                formatter(val), ha="center", color=COLORS[i],
                fontsize=17, fontweight="bold")
    footer(fig, "5 independent runs/profile  |  120 s  |  8 threads  |  "
                "50 connections  |  Error bars: +/- 1 SD")
    save(fig, out, filename)


def make_all(groups, out):
    x = np.arange(len(PROFILES))

    standard_bars(groups, out, "off", "rps",
        "mTLS throughput under sustained load",
        "Verified full TLS handshakes | eBPF OFF | 5 independent runs",
        "HTTP requests / second", "01-mtls-throughput-dark",
        lambda v: f"{v:,.0f}", upper=1400)

    # This is the v3 elapsed metric, not the old successful-call duration.
    standard_bars(groups, out, "on", "ebpf_full_mean_ms",
        "mTLS handshake duration with eBPF",
        "Server-observed elapsed time from first SSL_do_handshake call | eBPF ON",
        "Observed handshake elapsed (ms)", "02-mtls-mean-handshake-dark",
        lambda v: f"{v:.2f}", upper=55)

    standard_bars(groups, out, "off", "latency_mean_ms",
        "Client-observed HTTP latency",
        "wrk mean request latency | eBPF OFF | TLS setup excluded",
        "Mean HTTP request latency (ms)", "03-mtls-http-latency-dark",
        lambda v: f"{v:.2f}", upper=50)

    # Reproducibility, same line weights/markers/layout as the historical plot.
    fig, ax = make_figure(
        "mTLS benchmark reproducibility",
        "HTTP throughput across five independent rounds | eBPF OFF",
        "HTTP requests / second")
    for i, profile in enumerate(PROFILES):
        points = values(groups, "off", profile, "rps")
        ax.plot([1,2,3,4,5], points, marker=["o", "s", "D", "^"][i],
                markersize=10, linewidth=2.5, color=COLORS[i],
                markeredgecolor=BG, markeredgewidth=1.2,
                label=LABELS[i].replace("\n", " "))
    ax.set_xticks([1,2,3,4,5]); ax.set_xlim(.75, 5.25)
    ax.set_ylim(820, 1200)
    ax.set_xlabel("Benchmark round", fontsize=13, labelpad=12)
    ax.legend(loc="upper right", frameon=False, labelcolor=FG, ncol=2)
    footer(fig, "5 independent 120-second runs/profile  |  Verified peer  |  "
                "Session resumption disabled")
    save(fig, out, "04-mtls-reproducibility-dark")

    standard_bars(groups, out, "off", "cpu_busy_pct",
        "Server CPU utilization under mTLS load",
        "Mean system-level CPU busy | eBPF OFF | 5 independent runs",
        "CPU utilization (%)", "05-mtls-cpu-utilization-dark",
        lambda v: f"{v:.2f}%", upper=110)

    # Relative throughput penalty for enabling full observer stack.
    on, _ = summary(groups, "on", "rps")
    off, _ = summary(groups, "off", "rps")
    penalties = 100 * (off - on) / off
    fig, ax = make_figure(
        "Observed impact of TLS instrumentation",
        "Throughput reduction from exporter OFF to ON | 5 runs per mode/profile",
        "Throughput reduction (%)")
    bars = ax.bar(x, penalties, width=0.62, color=COLORS)
    ax.set_xticks(x, LABELS)
    ax.set_ylim(0, max(9, max(penalties) * 1.3))
    for i, (bar, val) in enumerate(zip(bars, penalties)):
        ax.text(bar.get_x()+bar.get_width()/2, val+0.22, f"{val:.2f}%",
                ha="center", color=COLORS[i], fontsize=17, fontweight="bold")
    footer(fig, "Observed exporter + eBPF overhead; not isolated probe CPU cost  |  "
                "120 s runs, 8 threads, 50 connections")
    save(fig, out, "06-mtls-observer-overhead-dark")

    # Controlled X25519 -> Hybrid difference, round-paired.
    base = values(groups, "off", "mtls-x25519", "rps")
    hybrid = values(groups, "off", "mtls-hybrid", "rps")
    delta_rps = hybrid - base
    delta_pct = 100 * (hybrid/base - 1)
    mean_d = float(np.mean(delta_rps)); sd_d = float(np.std(delta_rps, ddof=1))
    ci_half = T_95_DF4 * sd_d / math.sqrt(len(delta_rps))
    fig, ax = make_figure(
        "Hybrid vs X25519: throughput difference",
        "Same ECDSA P-384 authentication | Paired by benchmark round | eBPF OFF",
        "Hybrid minus X25519 (requests/s)")
    bars = ax.bar(np.arange(1, 6), delta_rps, width=0.65, color=HYBRID)
    ax.axhline(0, color=FG, linewidth=1.2, alpha=0.8)
    ax.axhline(mean_d, color=X25519, linestyle="--", linewidth=2.0,
               label=f"Mean: {mean_d:+.2f} RPS ({np.mean(delta_pct):+.2f}% mean paired change)")
    ax.set_xticks([1,2,3,4,5]); ax.set_xlim(.45, 5.55)
    ax.set_xlabel("Benchmark round", fontsize=13, labelpad=12)
    ax.set_ylim(min(-65, min(delta_rps) * 1.25), 8)
    for bar, val in zip(bars, delta_rps):
        ax.text(bar.get_x()+bar.get_width()/2, val-2.0,
                f"{val:+.1f}", ha="center", va="top",
                color=FG, fontsize=13, fontweight="bold")
    ax.legend(loc="upper right", frameon=False, labelcolor=FG)
    footer(fig, f"Mean difference: {mean_d:+.2f} RPS  |  "
                f"Paired 95% CI: [{mean_d-ci_half:+.2f}, {mean_d+ci_half:+.2f}] RPS  |  "
                "n=5 rounds")
    save(fig, out, "07-mtls-hybrid-vs-x25519-dark")

    # OFF/ON view for all modes, to avoid conflating the two measurement regimes.
    fig, ax = make_figure(
        "mTLS throughput: observer OFF vs ON",
        "Same four TLS profiles | Separate performance and observability campaigns",
        "HTTP requests / second")
    width = 0.29
    b_off = ax.bar(x-width/2, off, width=width, color=COLORS, alpha=1.0, label="eBPF OFF")
    b_on = ax.bar(x+width/2, on, width=width, color=COLORS, alpha=0.48, label="eBPF ON")
    ax.set_xticks(x, LABELS); ax.set_ylim(0, 1350)
    for bars in (b_off, b_on):
        for bar in bars:
            val = bar.get_height()
            ax.text(bar.get_x()+bar.get_width()/2, val+14,
                    f"{val:,.0f}", ha="center", fontsize=11.5, color=FG)
    ax.legend(loc="upper right", frameon=False, labelcolor=FG, ncol=2)
    footer(fig, "5 x 120 s runs/profile/mode  |  "
                "RPS OFF used for performance conclusions; ON for eBPF observation")
    save(fig, out, "08-mtls-throughput-on-off-dark")

    # Unambiguous local summary without hostnames, IPs, or certificate paths.
    lines = [
        "MTLS FOUR-PROFILE CAMPAIGN — FIGURE SUMMARY", "",
        "Same visual style as original mtls/scripts/plot-mtls-dark.py", "",
        "Profile | RPS OFF mean | RPS OFF SD | Handshake elapsed ON mean (ms) | Observed OFF-to-ON RPS penalty (%)",
        "--- | ---: | ---: | ---: | ---:",
    ]
    for i, p in enumerate(PROFILES):
        v = values(groups, "off", p, "rps")
        h = values(groups, "on", p, "ebpf_full_mean_ms")
        lines.append(f"{p} | {np.mean(v):.2f} | {np.std(v,ddof=1):.2f} | "
                     f"{np.mean(h):.3f} | {penalties[i]:.2f}")
    lines += ["", "Cautions:",
              "- wrk HTTP latency excludes TLS connection setup.",
              "- eBPF elapsed starts at the first server-observed SSL_do_handshake call.",
              "- ON vs OFF includes exporter activity, parsing and polling.",
              "- CPU busy is system-level and not isolated crypto CPU time.",
              "- Confidence interval shown in figure 07 is a t-based paired interval (n=5).",
              "- No server addresses, internal hostnames, keys or certificate data are included.", ""]
    (out / "FIGURE_SUMMARY.txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"\nGenerated 8 matching-theme figures (24 files) in: {out}")
    print("Summary:", out / "FIGURE_SUMMARY.txt")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, help="results.csv from a complete 40-run mTLS campaign")
    parser.add_argument("--out", type=Path, help="Output folder; default: <csv folder>/figures/dark")
    args = parser.parse_args()
    try:
        path = args.csv.expanduser() if args.csv else latest_input()
        if not path.is_file():
            raise ValueError(f"Input CSV does not exist: {path}")
        data = read_verified_csv(path)
        out = args.out.expanduser() if args.out else path.parent / "figures" / "dark"
        out.mkdir(parents=True, exist_ok=True)
        print("Input:", path)
        print("Output:", out)
        make_all(data, out)
        return 0
    except (ValueError, OSError) as exc:
        print("ERROR:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())