#!/usr/bin/env python3

import csv
import statistics as stats
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch

BASE = Path(__file__).resolve().parent
DATA = BASE.parent / "benchmarks" / "2026-11-04-stability"
OUT = BASE / "figures" / "dark"
OUT.mkdir(parents=True, exist_ok=True)

PROFILES = [
    "classic-a2",
    "classic-c2",
    "pqc-a1",
    "pqc-b1",
    "pqc-c1",
]

LABELS = [
    "CLASSIC\nA.2",
    "CLASSIC\nC.2",
    "PQC\nA.1",
    "PQC\nB.1",
    "PQC\nC.1",
]

BG = "#0B111A"
FG = "#F5F7FA"
MUTED = "#A0AEC0"
GRID = "#293746"
BLUE = "#249BFA"
CORAL = "#FF624D"

COLORS = [BLUE, BLUE, CORAL, CORAL, CORAL]

# November 4, 2026 stability campaign. Copy both stability CSVs beside this script.
import math
from collections import Counter

# Read the original 25 wrk measurements from CSV (no embedded results).
WRK = defaultdict(list)
with open(DATA / 'pqc_results_stability.csv', newline='') as f:
    for r in csv.DictReader(f):
        WRK[int(r['round'])].append((r['profile'], float(r['wrk_req_s']), float(r['wrk_p50_ms']), float(r['wrk_p99_ms'])))
assert len(WRK) == 5 and all(len(v) == 5 for v in WRK.values())

def quantile(bucket_counts, q):
    pairs=sorted(((float(k),v) for k,v in bucket_counts.items() if k!='+Inf'),key=lambda t:t[0])
    total=bucket_counts['+Inf']
    target=q*total
    lower_bound=0.0
    lower_count=0.0
    for upper_bound, upper_count in pairs:
        if upper_count >= target:
            if upper_count <= lower_count: return upper_bound*1000
            return (lower_bound+(upper_bound-lower_bound)*(target-lower_count)/(upper_count-lower_count))*1000
        lower_bound,lower_count=upper_bound,upper_count
    return float('nan') # quantile in +Inf bucket is not identifiable

with open(DATA / 'pqc_cpu_stability.csv',newline='') as f:
    prom=list(csv.DictReader(f))
with open(DATA / 'pqc_histogram_buckets_stability.csv',newline='') as f:
    bucket_rows=list(csv.DictReader(f))
assert len(prom)==25 and len(bucket_rows)==525, 'Unexpected CSV row counts'
per_run=defaultdict(dict)
for b in bucket_rows:
    key=(int(b['round']),b['profile'])
    le=b['le']
    if le in per_run[key]: raise ValueError(f'Duplicate bucket: {key} {le}')
    per_run[key][le]=float(b['bucket_increase'])
assert len(per_run)==25 and all(len(v)==21 for v in per_run.values())
pooled=defaultdict(lambda:defaultdict(float))
for (rnd,profile),bs in per_run.items():
    prev=-1.0
    for le in sorted(bs,key=lambda s:float('inf') if s=='+Inf' else float(s)):
        if bs[le]+1e-6 < prev: raise ValueError(f'Non-monotonic histogram: {rnd}/{profile}')
        prev=bs[le]
        pooled[profile][le]+=bs[le]

rows=[]
for m in prom:
    rnd=int(m['round']); profile=m['profile']
    match=[v for p,v,*_ in WRK[rnd] if p==profile]
    if len(match)!=1: raise ValueError(f'Missing wrk run: {rnd}/{profile}')
    wrk=next((entry for entry in WRK[rnd] if entry[0]==profile))
    b=per_run[(rnd,profile)]
    rows.append({'round':rnd,'profile':profile,'wrk_req_s':wrk[1],
                 'wrk_p50_ms':wrk[2],'wrk_p99_ms':wrk[3],
                 'cpu_mean_pct':float(m['web_cpu_busy_pct']),
                 **{f'ebpf_p{int(q*100)}_ms':quantile(b,q) for q in (.5,.95,.99)}})
assert len(rows)==25

groups=defaultdict(list)
for row in rows: groups[row['profile']].append(row)
assert all(len(groups[p])==5 for p in PROFILES)

# For eBPF chart bars, use pooled quantiles; run-to-run SD remains an error bar.
POOLED_Q={p:{f'ebpf_p{int(q*100)}_ms':quantile(bs,q) for q in (.5,.95,.99)}
          for p,bs in pooled.items()}

def summary(metric):
    means = []
    stds = []

    for profile in PROFILES:
        values = [float(r[metric]) for r in groups[profile]]
        means.append(POOLED_Q[profile][metric] if metric.startswith('ebpf_p') else stats.mean(values))
        stds.append(stats.stdev(values))

    return np.array(means), np.array(stds)

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

def make_figure(title, subtitle, ylabel, ylim=None):
    fig, ax = plt.subplots(figsize=(16, 9))

    fig.subplots_adjust(
        left=0.09,
        right=0.96,
        top=0.73,
        bottom=0.20,
    )

    fig.text(
        0.09, 0.92, title,
        fontsize=25, fontweight="bold",
        color=FG,
    )

    fig.text(
        0.09, 0.865, subtitle,
        fontsize=13, color=MUTED,
    )

    ax.set_ylabel(ylabel, fontsize=13, labelpad=15)

    ax.grid(axis="y", linestyle="--")
    ax.set_axisbelow(True)

    for side in ["top", "right", "left"]:
        ax.spines[side].set_visible(False)

    ax.spines["bottom"].set_color(GRID)

    ax.tick_params(axis="both", length=0, pad=9)

    if ylim is not None:
        ax.set_ylim(*ylim)

    return fig, ax

def footer(fig, text):
    fig.text(
        0.09, 0.095,
        text,
        fontsize=10.5,
        color=MUTED,
    )

def save(fig, name):
    for ext in ("png", "pdf", "svg"):
        fig.savefig(
            OUT / f"{name}.{ext}",
            dpi=300,
            facecolor=BG,
        )

    plt.close(fig)
    print(f"Created: {name} (PNG, PDF, SVG)")

x = np.arange(len(PROFILES))

legend = [
    Patch(facecolor=BLUE, label="Classical TLS"),
    Patch(facecolor=CORAL, label="Post-quantum TLS"),
]

# --------------------------------------------------
# FIGURE 1: THROUGHPUT
# --------------------------------------------------

means, stds = summary("wrk_req_s")

fig, ax = make_figure(
    "TLS throughput under sustained load",
    "Mean HTTP requests per second | 5 independent runs",
    "HTTP requests / second",
    (0, 2200),
)

bars = ax.bar(
    x,
    means,
    width=0.62,
    color=COLORS,
    edgecolor="none",
    yerr=stds,
    capsize=5,
    error_kw={
        "ecolor": FG,
        "elinewidth": 1.7,
        "capthick": 1.7,
    },
)

ax.set_xticks(x, LABELS)
ax.legend(
    handles=legend,
    loc="upper right",
    frameon=False,
    labelcolor=FG,
    ncol=2,
    bbox_to_anchor=(1, 1.25),
)

baseline = means[0]

for i, (bar, value, sd) in enumerate(zip(bars, means, stds)):
    center = bar.get_x() + bar.get_width() / 2

    ax.text(
        center,
        value + sd + 35,
        f"{value:,.0f}",
        ha="center",
        va="bottom",
        color=COLORS[i],
        fontsize=17,
        fontweight="bold",
    )

    if i >= 2:
        delta = (value / baseline - 1) * 100

        ax.text(
            center,
            value * 0.52,
            f"{delta:.1f}%\nvs. P-384",
            ha="center",
            va="center",
            color=FG,
            fontsize=14,
            fontweight="bold",
            linespacing=1.5,
            bbox={
                "boxstyle": "round,pad=0.55",
                "facecolor": "#7B2B28",
                "edgecolor": "none",
                "alpha": 0.85,
            },
        )

footer(
    fig,
    "5 runs/profile  |  120 s  |  8 threads  |  "
    "50 connections  |  Error bars: ±1 SD",
)

save(fig, "01-throughput-dark")

# --------------------------------------------------
# FIGURE 2: eBPF LATENCY
# --------------------------------------------------

fig, ax = make_figure(
    "TLS handshake instrumentation with eBPF",
    "Successful SSL_do_handshake() call duration",
    "Duration (ms)",
    (0, 280),
)

width = 0.23

metrics = [
    ("ebpf_p50_ms", "p50", 0.42),
    ("ebpf_p95_ms", "p95", 0.70),
    ("ebpf_p99_ms", "p99", 1.00),
]

for j, (metric, quantile, alpha) in enumerate(metrics):
    means, stds = summary(metric)

    ax.bar(
        x + (j - 1) * width,
        means,
        width=width,
        color=COLORS,
        alpha=alpha,
        yerr=stds,
        capsize=3,
        error_kw={
            "ecolor": FG,
            "elinewidth": 1,
        },
        label=quantile,
    )

ax.set_xticks(x, LABELS)

ax.legend(
    loc="upper right",
    frameon=False,
    labelcolor=FG,
    ncol=3,
)

footer(
    fig,
    "p50 / p95 / p99: pooled per-run Prometheus histogram increases  |  Error bars: ±1 SD of run quantiles",
)

save(fig, "02-ebpf-latency-dark")

# --------------------------------------------------
# FIGURE 3: CPU
# --------------------------------------------------

means, stds = summary("cpu_mean_pct")

fig, ax = make_figure(
    "Server CPU utilization",
    "CPU consumption during sustained TLS benchmarks",
    "CPU utilization (%)",
    (0, 105),
)

bars = ax.bar(
    x,
    means,
    width=0.62,
    color=COLORS,
    yerr=stds,
    capsize=5,
    error_kw={
        "ecolor": FG,
        "elinewidth": 1.5,
    },
)

ax.set_xticks(x, LABELS)

for i, (bar, value, sd) in enumerate(zip(bars, means, stds)):
    ax.text(
        bar.get_x() + bar.get_width() / 2,
        value + sd + 1.5,
        f"{value:.1f}%",
        ha="center",
        color=COLORS[i],
        fontsize=16,
        fontweight="bold",
    )

footer(
    fig,
    "RHEL 9.8  |  Apache 2.4.62  |  "
    "OpenSSL 3.5.8  |  4 vCPU server  |  Error bars: ±1 SD",
)

save(fig, "03-cpu-dark")



# --------------------------------------------------
# FIGURE 4: THROUGHPUT VS eBPF p99
# --------------------------------------------------

throughput, throughput_sd = summary("wrk_req_s")
p99, p99_sd = summary("ebpf_p99_ms")

fig, ax = make_figure(
    "Throughput vs. TLS handshake call latency",
    "Mean throughput and eBPF p99 | 5 independent runs per profile",
    "Successful SSL_do_handshake() p99 (ms)",
)

for i, profile in enumerate(PROFILES):
    ax.errorbar(
        throughput[i], p99[i],
        xerr=throughput_sd[i],
        yerr=p99_sd[i],
        fmt="o",
        markersize=13,
        color=COLORS[i],
        ecolor=FG,
        elinewidth=1.3,
        capsize=4,
    )

    ax.annotate(
        LABELS[i].replace("\n", " "),
        (throughput[i], p99[i]),
        xytext=(0, 17 if i % 2 == 0 else -23),
        textcoords="offset points",
        ha="center",
        color=FG,
        fontsize=11,
    )

ax.set_xlabel("HTTP requests / second", fontsize=13, labelpad=12)
ax.set_xlim(1150, 2050)
ax.set_ylim(95, 255)

footer(
    fig,
    "Each point: mean of 5 runs  |  Error bars: ±1 SD  |  "
    "eBPF p99: pooled histogram quantile; error bars: ±1 SD of run quantiles",
)

save(fig, "04-throughput-vs-p99-dark")

# --------------------------------------------------
# FIGURE 5: REPRODUCIBILITY ACROSS ROUNDS
# --------------------------------------------------

# --------------------------------------------------
# FIGURE 5: REPRODUCIBILITY ACROSS ROUNDS
# --------------------------------------------------

fig, ax = make_figure(
    "Benchmark reproducibility",
    "HTTP throughput across five independent rounds",
    "HTTP requests / second",
)

rounds = np.arange(1, 6)

line_colors = [
    "#249BFA",  # ECDSA P-384
    "#77D3FF",  # ECDSA P-521
    "#FF624D",  # PQC A1
    "#FFB347",  # PQC B1
    "#B58CFF",  # PQC C1
]

markers = ["o", "D", "^", "s", "X"]
linestyles = ["-", "--", "-", "--", "-."]

# Small horizontal offsets to distinguish overlapping series
offsets = [0, 0, 0, -0.045, 0.045]

for i, profile in enumerate(PROFILES):
    profile_rows = sorted(
        groups[profile],
        key=lambda r: int(r["round"])
    )

    values = [
        float(r["wrk_req_s"])
        for r in profile_rows
    ]

    ax.plot(
        rounds + offsets[i],
        values,
        marker=markers[i],
        markersize=10,
        linewidth=2.5,
        color=line_colors[i],
        linestyle=linestyles[i],
        markeredgecolor=BG,
        markeredgewidth=1.2,
        label=LABELS[i].replace("\n", " "),
        zorder=5 + i,
    )

ax.set_xticks(rounds)
ax.set_xlim(0.75, 5.25)
ax.set_xlabel("Benchmark round", fontsize=13, labelpad=12)
ax.set_ylim(1150, 2000)

ax.legend(
    loc="upper right",
    frameon=False,
    labelcolor=FG,
    ncol=3,
    fontsize=11,
)

footer(
    fig,
    "5 independent 120-second runs/profile  |  "
    "Small horizontal offsets for overlapping markers; "
    "throughput values unchanged",
)

save(fig, "05-reproducibility-dark")
# --------------------------------------------------
# FIGURE 6: RELATIVE THROUGHPUT PENALTY
# --------------------------------------------------

throughput, throughput_sd = summary("wrk_req_s")
baseline = throughput[0]

penalty = (1 - throughput[1:] / baseline) * 100

fig, ax = make_figure(
    "Relative throughput reduction",
    "Comparison against the CLASSIC A.2 baseline",
    "Throughput reduction (%)",
    (0, 30),
)

bars = ax.bar(
    np.arange(4),
    penalty,
    width=0.60,
    color=COLORS[1:],
)

ax.set_xticks(
    np.arange(4),
    LABELS[1:],
)

for bar, value in zip(bars, penalty):
    ax.text(
        bar.get_x() + bar.get_width() / 2,
        value + 0.7,
        f"{value:.1f}%",
        ha="center",
        color=FG,
        fontsize=17,
        fontweight="bold",
    )

footer(
    fig,
    "Baseline: CLASSIC A.2 (classic-a2)  |  "
    "Calculated from mean requests/second across five runs",
)

save(fig, "06-relative-throughput-dark")

# --------------------------------------------------
# FIGURE 7: CLIENT-SIDE LATENCY (wrk)
# --------------------------------------------------

fig, ax = make_figure(
    "Client-observed HTTP latency",
    "wrk request latency under sustained TLS load",
    "HTTP request latency (ms)",
    (0, 210),
)

width = 0.32

for j, (metric, label, alpha) in enumerate([
    ("wrk_p50_ms", "p50", 0.55),
    ("wrk_p99_ms", "p99", 1.0),
]):
    means, stds = summary(metric)

    ax.bar(
        x + (j - 0.5) * width,
        means,
        width=width,
        color=COLORS,
        alpha=alpha,
        yerr=stds,
        capsize=4,
        error_kw={"ecolor": FG},
        label=label,
    )

ax.set_xticks(x, LABELS)

ax.legend(
    loc="upper right",
    frameon=False,
    labelcolor=FG,
    ncol=2,
)

footer(
    fig,
    "Client-observed HTTP request latency  |  "
    "p50/p99 averaged across five runs  |  Error bars: ±1 SD",
)

save(fig, "07-wrk-latency-dark")

print(f"\nAll seven figures saved in: {OUT}")
