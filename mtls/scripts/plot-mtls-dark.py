#!/usr/bin/env python3
import csv
import re
import statistics as stats
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "data"
OUT = BASE / "figures" / "dark"
OUT.mkdir(parents=True, exist_ok=True)

PROFILES = ["mtls-classic", "mtls-hybrid", "mtls-pqc"]
LABELS = ["Classic\nECDSA P-384", "Hybrid\nECDSA + ML-KEM", "PQC\nML-DSA-65"]

BG = "#0B111A"
FG = "#F5F7FA"
MUTED = "#A0AEC0"
GRID = "#293746"
COLORS = ["#249BFA", "#B58CFF", "#FF624D"]

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

def parse_log(path):
    text = path.read_text()
    def get(pattern):
        m = re.search(pattern, text, re.MULTILINE)
        if not m:
            raise ValueError(f"Missing {pattern} in {path}")
        return float(m.group(1))

    return {
        "wrk_req_s": get(r"^Requests/sec:\s+([\d.]+)"),
        "wrk_p50_ms": get(r"^\s*50%\s+([\d.]+)ms"),
        "wrk_p90_ms": get(r"^\s*90%\s+([\d.]+)ms"),
        "wrk_p99_ms": get(r"^\s*99%\s+([\d.]+)ms"),
    }

with (BASE / "results" / "mtls-consolidated.csv").open() as f:
    rows = list(csv.DictReader(f))

assert len(rows) == 9

groups = defaultdict(list)
for row in rows:
    row.update(parse_log(DATA / row["logfile"]))
    groups[row["profile"]].append(row)

assert all(len(groups[p]) == 3 for p in PROFILES)

def summary(metric):
    means, stds = [], []
    for p in PROFILES:
        values = [float(r[metric]) for r in groups[p]]
        means.append(stats.mean(values))
        stds.append(stats.stdev(values))
    return np.array(means), np.array(stds)

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

def save(fig, name):
    for ext in ("png", "pdf", "svg"):
        fig.savefig(OUT / f"{name}.{ext}", dpi=300, facecolor=BG)
    plt.close(fig)
    print(f"Created: {name} (PNG, PDF, SVG)")

x = np.arange(3)

def bar_chart(metric, title, subtitle, ylabel, name, ylim=None, fmt=".1f"):
    means, stds = summary(metric)
    fig, ax = make_figure(title, subtitle, ylabel)
    bars = ax.bar(
        x, means, width=0.62, color=COLORS,
        yerr=stds, capsize=5,
        error_kw={"ecolor": FG, "elinewidth": 1.7, "capthick": 1.7}
    )
    ax.set_xticks(x, LABELS)
    if ylim:
        ax.set_ylim(*ylim)
    else:
        ax.set_ylim(0, max(means + stds) * 1.22)

    for i, (bar, value, sd) in enumerate(zip(bars, means, stds)):
        ax.text(
            bar.get_x() + bar.get_width()/2,
            value + sd + max(means)*0.025,
            format(value, fmt),
            ha="center", color=COLORS[i],
            fontsize=17, fontweight="bold"
        )

    footer(fig, "3 independent runs/profile  |  120 s  |  8 threads  |  "
                "50 connections  |  Error bars: +/- 1 SD")
    save(fig, name)

bar_chart(
    "wrk_req_s",
    "mTLS throughput under sustained load",
    "Verified full TLS handshakes | Mean of 3 independent runs",
    "HTTP requests / second",
    "01-mtls-throughput-dark",
    (0, 1400),
    ",.0f"
)

bar_chart(
    "mean_ms",
    "mTLS handshake duration with eBPF",
    "Mean successful SSL_do_handshake() call duration",
    "Duration (ms)",
    "02-mtls-mean-handshake-dark",
    (0, 55)
)

# Percentile comparison
fig, ax = make_figure(
    "mTLS handshake latency distribution",
    "eBPF histogram quantiles | Mean of 3 independent runs",
    "SSL_do_handshake() duration (ms)"
)

width = 0.23
for j, (metric, alpha) in enumerate([
    ("p50_ms", 0.42),
    ("p95_ms", 0.70),
    ("p99_ms", 1.00),
]):
    means, stds = summary(metric)
    ax.bar(
        x + (j-1)*width, means, width=width,
        color=COLORS, alpha=alpha,
        yerr=stds, capsize=3,
        error_kw={"ecolor": FG, "elinewidth": 1},
        label=metric.replace("_ms", "")
    )

ax.set_xticks(x, LABELS)
ax.set_ylim(0, 270)
ax.legend(loc="upper right", frameon=False, labelcolor=FG, ncol=3)
footer(fig, "p50/p95/p99: mean of per-run histogram quantiles  |  "
            "Error bars: +/- 1 SD")
save(fig, "03-mtls-ebpf-percentiles-dark")

# HTTP latency
fig, ax = make_figure(
    "Client-observed HTTP latency",
    "wrk request latency under sustained verified mTLS load",
    "HTTP request latency (ms)"
)

width = 0.32
for j, (metric, alpha) in enumerate([
    ("wrk_p50_ms", 0.55),
    ("wrk_p99_ms", 1.0),
]):
    means, stds = summary(metric)
    ax.bar(
        x + (j-0.5)*width, means, width=width,
        color=COLORS, alpha=alpha,
        yerr=stds, capsize=4,
        error_kw={"ecolor": FG},
        label=metric.replace("wrk_", "").replace("_ms", "")
    )

ax.set_xticks(x, LABELS)
ax.set_ylim(0, None)
ax.legend(loc="upper right", frameon=False, labelcolor=FG, ncol=2)
footer(fig, "Client-observed HTTP request latency  |  "
            "3 runs/profile  |  Error bars: +/- 1 SD")
save(fig, "04-mtls-http-latency-dark")

# Reproducibility
fig, ax = make_figure(
    "mTLS benchmark reproducibility",
    "HTTP throughput across three independent rounds",
    "HTTP requests / second"
)

for i, profile in enumerate(PROFILES):
    ordered = sorted(groups[profile], key=lambda r: int(r["round"]))
    values = [float(r["wrk_req_s"]) for r in ordered]
    ax.plot(
        [1, 2, 3], values,
        marker=["o", "D", "^"][i],
        markersize=10, linewidth=2.5,
        color=COLORS[i],
        markeredgecolor=BG,
        markeredgewidth=1.2,
        label=LABELS[i].replace("\n", " ")
    )

ax.set_xticks([1, 2, 3])
ax.set_xlim(0.75, 3.25)
ax.set_ylim(850, 1200)
ax.set_xlabel("Benchmark round", fontsize=13, labelpad=12)
ax.legend(loc="upper right", frameon=False, labelcolor=FG)
footer(fig, "3 independent 120-second runs/profile  |  "
            "Full TLS handshakes; session resumption disabled")
save(fig, "05-mtls-reproducibility-dark")

print(f"\nAll figures saved in: {OUT}")

# --------------------------------------------------
# CPU ANALYSIS - EXACT 120-SECOND WINDOWS
# --------------------------------------------------

with (DATA / "cpu-120s.csv").open() as f:
    cpu_rows = list(csv.DictReader(f))

assert len(cpu_rows) == 9
cpu_groups = defaultdict(list)

for row in cpu_rows:
    cpu_groups[row["profile"]].append(row)

assert all(len(cpu_groups[p]) == 3 for p in PROFILES)

def cpu_summary(metric):
    means, stds = [], []
    for profile in PROFILES:
        values = [float(r[metric]) for r in cpu_groups[profile]]
        means.append(stats.mean(values))
        stds.append(stats.stdev(values))
    return np.array(means), np.array(stds)

# FIGURE 6: CPU UTILIZATION

means, stds = cpu_summary("busy_pct")

fig, ax = make_figure(
    "Server CPU utilization under mTLS load",
    "Mean CPU utilization across three independent 120-second runs",
    "CPU utilization (%)"
)

bars = ax.bar(
    x, means, width=0.62, color=COLORS,
    yerr=stds, capsize=5,
    error_kw={"ecolor": FG, "elinewidth": 1.7}
)

ax.set_xticks(x, LABELS)
ax.set_ylim(0, 105)

for i, (bar, value, sd) in enumerate(zip(bars, means, stds)):
    ax.text(
        bar.get_x() + bar.get_width()/2,
        value + sd + 1.5,
        f"{value:.2f}%",
        ha="center", color=COLORS[i],
        fontsize=17, fontweight="bold"
    )

footer(fig, "4 vCPU server  |  Exact 120-second CPU windows  |  "
            "Error bars: +/- 1 SD")
save(fig, "06-mtls-cpu-utilization-dark")

# FIGURE 7: CPU BREAKDOWN

fig, ax = make_figure(
    "CPU time distribution by mTLS profile",
    "User, system and interrupt CPU utilization",
    "CPU utilization (%)"
)

bottom = np.zeros(3)

for metric, label, alpha in [
    ("user_pct", "User", 1.0),
    ("system_pct", "System", 0.65),
    ("irq_pct", "IRQ + SoftIRQ", 0.35),
]:
    values, _ = cpu_summary(metric)

    ax.bar(
        x, values, bottom=bottom,
        width=0.62, color=COLORS,
        alpha=alpha, label=label
    )
    bottom += values

ax.set_xticks(x, LABELS)
ax.set_ylim(0, 105)
ax.legend(loc="upper right", frameon=False, labelcolor=FG, ncol=3)

footer(fig, "Mean CPU utilization across 3 runs  |  "
            "4 vCPU  |  Exact 120-second windows")
save(fig, "07-mtls-cpu-breakdown-dark")

# FIGURE 8: CPU EFFICIENCY

# Total CPU seconds used during each 120-second run,
# normalized per 1000 completed TLS handshakes.

efficiency_groups = defaultdict(list)

for row in cpu_rows:
    profile = row["profile"]
    round_number = int(row["round"])

    matches = [
        r for r in groups[profile]
        if int(r["round"]) == round_number
    ]
    assert len(matches) == 1

    handshakes = int(matches[0]["handshakes"])
    busy_pct = float(row["busy_pct"])

    cpu_seconds = busy_pct / 100 * 4 * 120
    cpu_per_1000 = cpu_seconds * 1000 / handshakes

    efficiency_groups[profile].append(cpu_per_1000)

means = np.array([
    stats.mean(efficiency_groups[p]) for p in PROFILES
])
stds = np.array([
    stats.stdev(efficiency_groups[p]) for p in PROFILES
])

fig, ax = make_figure(
    "CPU efficiency per 1,000 TLS handshakes",
    "Total server CPU consumption normalized by completed full handshakes",
    "CPU-seconds / 1,000 handshakes"
)

bars = ax.bar(
    x, means, width=0.62, color=COLORS,
    yerr=stds, capsize=5,
    error_kw={"ecolor": FG, "elinewidth": 1.7}
)

ax.set_xticks(x, LABELS)
ax.set_ylim(0, 5)

for i, (bar, value, sd) in enumerate(zip(bars, means, stds)):
    ax.text(
        bar.get_x() + bar.get_width()/2,
        value + sd + 0.12,
        f"{value:.3f}",
        ha="center", color=COLORS[i],
        fontsize=17, fontweight="bold"
    )

footer(fig, "4 vCPU x 120 s  |  3 runs/profile  |  "
            "Total server CPU, not cryptographic CPU time")
save(fig, "08-mtls-cpu-efficiency-dark")

print("\nCPU figures completed.")
