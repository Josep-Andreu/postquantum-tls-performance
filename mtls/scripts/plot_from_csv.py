#!/usr/bin/env python3
"""Regenerate eight mTLS charts from published run-level measurements.

Newly generated charts are for independent exploration; the historical original
charts can be imported separately from the author's archived artifact bundle.
"""
import csv
from pathlib import Path
import statistics as st
from collections import defaultdict
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"figures/generated"
OUT.mkdir(parents=True,exist_ok=True)
with (ROOT/"data/runs.csv").open(newline="") as f:
    rows=list(csv.DictReader(f))
order=["mtls-classic","mtls-hybrid","mtls-pqc"]
labels=["Classic\nECDSA P-384","Hybrid\nECDSA + hybrid KEM","PQC auth\nML-DSA-65"]
colors=["#249BFA","#B58CFF","#FF624D"]
group={k:[r for r in rows if r["profile"]==k] for k in order}
def summary(column):
    samples=[[float(r[column]) for r in group[p]] for p in order]
    return np.array([st.mean(a) for a in samples]), np.array([st.stdev(a) for a in samples])
def save(fig,name):
    for ext in ("png","svg","pdf"):
        fig.savefig(OUT/(name+"."+ext),dpi=250,bbox_inches="tight")
    plt.close(fig)
def bars(name,title,ylabel,column,ylim=None):
    mean,sd=summary(column)
    fig,ax=plt.subplots(figsize=(14,8))
    ax.bar(labels,mean,yerr=sd,capsize=5,color=colors)
    ax.set(title=title,ylabel=ylabel)
    ax.set_ylim(0,ylim if ylim else max(mean+sd)*1.25)
    ax.grid(axis="y",alpha=.2)
    fig.text(.1,.015,"3 runs/profile • 120 seconds • 50 concurrent connections • error bars ±1 sample SD",fontsize=10)
    save(fig,name)
bars("01-mtls-throughput","mTLS throughput under sustained load","HTTP requests / second","wrk_requests_per_sec",1400)
bars("02-mtls-mean-handshake","Mean eBPF-observed SSL_do_handshake() call duration","Milliseconds","ebpf_mean_ms",55)
x=np.arange(3)
fig,ax=plt.subplots(figsize=(14,8))
for i,col in enumerate(["ebpf_p50_ms","ebpf_p95_ms","ebpf_p99_ms"]):
    mean,sd=summary(col)
    ax.bar(x+(i-1)*.23,mean,width=.23,label=col.split("_")[1],alpha=[.5,.72,1][i],yerr=sd,capsize=2)
ax.set_xticks(x,labels)
ax.set(title="TLS call-duration percentiles (eBPF histogram estimates)",ylabel="Milliseconds")
ax.legend()
save(fig,"03-mtls-ebpf-percentiles")
fig,ax=plt.subplots(figsize=(14,8))
for i,col in enumerate(["wrk_http_p50_ms","wrk_http_p99_ms"]):
    mean,sd=summary(col)
    ax.bar(x+(i-.5)*.35,mean,width=.35,label="HTTP "+col.split("_")[2],alpha=[.6,1][i],yerr=sd,capsize=3)
ax.set_xticks(x,labels)
ax.set(title="Client-observed HTTP latency under mTLS",ylabel="Milliseconds")
ax.legend()
save(fig,"04-mtls-http-latency")
fig,ax=plt.subplots(figsize=(14,8))
for i,p in enumerate(order):
    vals=[float(r["wrk_requests_per_sec"]) for r in sorted(group[p],key=lambda r:int(r["round"]))]
    ax.plot([1,2,3],vals,label=labels[i].replace("\n"," "),marker="o",color=colors[i],linewidth=3)
ax.set(title="mTLS reproducibility across three rounds",xlabel="Round",ylabel="HTTP requests / second",xticks=[1,2,3])
ax.legend()
save(fig,"05-mtls-reproducibility")
bars("06-mtls-cpu-utilization","Server CPU busy under mTLS","CPU busy (%)","cpu_busy_pct",105)
fig,ax=plt.subplots(figsize=(14,8))
bottom=np.zeros(3)
for col,label,alpha in [("cpu_user_pct","User",1),("cpu_system_pct","System",.7),("cpu_irq_pct","IRQ + softIRQ",.4)]:
    vals,_=summary(col)
    ax.bar(labels,vals,bottom=bottom,color=colors,alpha=alpha,label=label)
    bottom+=vals
ax.set(title="CPU distribution by mTLS profile",ylabel="CPU utilization (%)",ylim=(0,105))
ax.legend()
save(fig,"07-mtls-cpu-breakdown")
for r in rows:
    r["eff"]=float(r["cpu_busy_pct"])/100*4*120*1000/int(r["handshakes_full"])
bars("08-mtls-cpu-efficiency","Total server CPU / 1,000 recorded full handshakes","CPU seconds / 1,000 handshakes","eff",5)
print("Wrote eight plot families (PNG/SVG/PDF) to",OUT)
