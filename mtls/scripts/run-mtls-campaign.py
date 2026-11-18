#!/usr/bin/env python3
"""Run repeatable four-profile mTLS benchmarks from the client host.

Uses an already-validated wrk-mtls-verify build on client and SSH to the web host.
No certificates/keys are copied. No GitHub access. The public SUMMARY.txt excludes
internal FQDNs and certificate paths; raw wrk logs remain in a private directory.

Default: 5 runs x 120s per profile with exporter OFF (primary throughput study).
Optional: --mode on for separately instrumented eBPF study, or --mode both.
"""
import argparse
import csv
import datetime
import json
import os
import random
import re
import shlex
import signal
import statistics
import subprocess
import sys
import time
from pathlib import Path

PROFILES = [
    ("mtls-classic", 13443, "client-ecdsa.crt", "client-ecdsa.key", "regular-A2.chain.pem", "secp384r1"),
    ("mtls-x25519", 16443, "client-ecdsa.crt", "client-ecdsa.key", "regular-A2.chain.pem", "x25519"),
    ("mtls-hybrid", 15443, "client-ecdsa.crt", "client-ecdsa.key", "regular-A2.chain.pem", "X25519MLKEM768"),
    ("mtls-pqc", 14443, "client-mldsa.crt", "client-mldsa.key", "regular-A1.chain.pem", "X25519MLKEM768"),
]
SERVICE = "pqc-tls-exporter.service"
METRICS = "http://127.0.0.1:9101/metrics"
FIELDS = ["mode", "round", "profile", "port", "rps", "http_requests", "tls_full", "tls_resumed",
          "latency_mean_ms", "cpu_busy_pct", "ebpf_completed", "ebpf_full_count", "ebpf_parse_errors",
          "ebpf_full_mean_ms", "wrk_exit"]


def ssh(args, script, timeout=60):
    cmd = ["ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "-o", "ServerAliveInterval=20",
           f"{args.ssh_user}@{args.web_host}", "bash", "-se"]
    p = subprocess.run(cmd, input=script, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    if p.returncode:
        raise RuntimeError(f"Remote operation failed ({p.returncode}): {p.stderr[-700:] or p.stdout[-700:]}")
    return p.stdout


def wait_observer(args):
    out = ssh(args, f'''set -e
for i in $(seq 1 30); do
  if curl -fsS --max-time 4 {METRICS} 2>/dev/null | grep -qx 'tls_observer_up 1.0'; then
     echo READY
     exit 0
  fi
  sleep 1
done
exit 1
''', timeout=75)
    if "READY" not in out:
        raise RuntimeError("Observer did not become ready")


def change_state(args, mode):
    if mode == "off":
        ssh(args, f'''set -eu
systemctl stop {SERVICE}
test "$(systemctl is-active {SERVICE} || true)" = inactive
if pgrep -f '[b]pftrace /opt/tls-observer/tls_handshake.bt' >/dev/null; then
  echo 'Unexpected probe still active' >&2; exit 1
fi
''')
    else:
        ssh(args, f"systemctl start {SERVICE}")
        wait_observer(args)
        # Only instrumented v3 metrics are valid for this run.
        ssh(args, "grep -q 'COMPLETE pid' /opt/tls-observer/tls_handshake.bt && "
                  "grep -q 'HANDSHAKE_FULL_ELAPSED' /root/pqc-observability/exporter/tls_exporter.py")


def select_profile(args, profile):
    ssh(args, "install -d -m 0755 /run/pqc-observability; "
              "printf '%s\\n' " + shlex.quote(profile) + " > /run/pqc-observability/profile")
    time.sleep(1)


def remote_cpu(args):
    s = ssh(args, "awk '/^cpu / { t=0; for (i=2;i<=NF;i++) t+=$i; print t, $5+$6; exit }' /proc/stat").strip()
    total, idle = map(int, s.split())
    return total, idle


def cpu_pct(a, b):
    total = b[0] - a[0]
    idle = b[1] - a[1]
    return round(100 * (total - idle) / total, 2) if total > 0 else None


def remote_metrics(args):
    return ssh(args, f"curl -fsS --max-time 8 {METRICS}")


def metric(text, name, labels=None):
    labels = labels or {}
    for line in text.splitlines():
        if not (line.startswith(name + "{") or line.startswith(name + " ")):
            continue
        if all(f'{k}="{v}"' in line for k, v in labels.items()):
            return float(line.split()[-1])
    return 0.0


def parse_wrk(text, group):
    def match(pattern):
        m = re.search(pattern, text, re.M | re.I)
        if not m:
            raise ValueError("Missing required wrk output field: " + pattern)
        return m.group(1)
    negotiated = match(r'^Negotiated group:\s*(\S+)')
    if negotiated.lower() != group.lower():
        raise ValueError("Wrong TLS group: " + negotiated)
    if match(r'^Protocol:\s*(\S+)') != "TLSv1.3":
        raise ValueError("TLS version is not TLS 1.3")
    if match(r'^Cipher:\s*(\S+)') != "TLS_AES_256_GCM_SHA384":
        raise ValueError("Unexpected cipher suite")
    lat_match = re.search(r'^\s*Latency\s+([\d.]+)(us|ms|s)\b', text, re.M)
    latency = None
    if lat_match:
        latency = float(lat_match.group(1)) * {"us": .001, "ms": 1., "s": 1000.}[lat_match.group(2)]
    result = dict(
        rps=float(match(r'^Requests/sec:\s+([\d.]+)')),
        http_requests=int(match(r'^\s*(\d+) requests in ')),
        tls_full=int(match(r'TLS handshake summary:\s*full=(\d+)')),
        tls_resumed=int(match(r'TLS handshake summary:\s*full=\d+\s+resumed=(\d+)')),
        latency_mean_ms=latency,
    )
    if result["rps"] <= 0 or result["http_requests"] <= 0 or result["tls_full"] <= 0:
        raise ValueError("No successful HTTP/TLS workload")
    if result["tls_resumed"]:
        raise ValueError("Resumed TLS handshakes detected; workload is not fully fresh")
    return result


def do_run(args, mode, round_n, profile, folder):
    label, port, cert, key, ca, group = profile
    tag = f"{mode}-round{round_n}-{label}"
    log = folder / (tag + ".log")
    print(f"▶ {tag} — {args.duration}s, {args.threads} threads, {args.connections} connections", flush=True)
    if mode == "on":
        select_profile(args, label)
        m0 = remote_metrics(args)
        if metric(m0, "tls_observer_up") != 1.0:
            raise RuntimeError("Exporter not healthy before run")
    else:
        m0 = None
    cpu0 = remote_cpu(args)
    env = os.environ.copy()
    env.update({"WRK_CLIENT_CERT": f"{args.cert_dir}/{cert}",
                "WRK_CLIENT_KEY": f"{args.cert_dir}/{key}",
                "WRK_CA_FILE": f"{args.cert_dir}/{ca}"})
    cmd = [args.wrk, f"-t{args.threads}", f"-c{args.connections}", f"-d{args.duration}s",
           "-H", "Connection: close", f"https://{args.server}:{port}/"]
    p = subprocess.run(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                       timeout=args.duration + 120)
    cpu1 = remote_cpu(args)
    log.write_text(p.stdout, encoding="utf-8")
    os.chmod(log, 0o600)
    if p.returncode:
        raise RuntimeError(f"wrk exited {p.returncode}: inspect private local log {log}")
    row = parse_wrk(p.stdout, group)
    row.update(mode=mode, round=round_n, profile=label, port=port,
               cpu_busy_pct=cpu_pct(cpu0, cpu1), wrk_exit=p.returncode,
               ebpf_completed="", ebpf_full_count="", ebpf_parse_errors="", ebpf_full_mean_ms="")
    if mode == "on":
        time.sleep(3)  # flush queued bpftrace/Python events before computing deltas
        m1 = remote_metrics(args)
        labels = {"profile": label}
        hs = metric(m1, "tls_handshakes_completed_total", labels) - metric(m0, "tls_handshakes_completed_total", labels)
        hist = metric(m1, "tls_handshake_full_elapsed_seconds_count", labels) - metric(m0, "tls_handshake_full_elapsed_seconds_count", labels)
        hsum = metric(m1, "tls_handshake_full_elapsed_seconds_sum", labels) - metric(m0, "tls_handshake_full_elapsed_seconds_sum", labels)
        errs = metric(m1, "tls_observer_parse_errors_total") - metric(m0, "tls_observer_parse_errors_total")
        row.update(ebpf_completed=int(round(hs)), ebpf_full_count=int(round(hist)),
                   ebpf_parse_errors=int(round(errs)),
                   ebpf_full_mean_ms=round(1000 * hsum / hist, 4) if hist > 0 else "")
        if hs != row["tls_full"] or hist != row["tls_full"] or errs != 0:
            raise RuntimeError(f"eBPF mismatch in {tag}: wrk={row['tls_full']} eBPF={hs} hist={hist} parser_delta={errs}")
    print(f"  RPS={row['rps']:.2f} HTTP={row['http_requests']} TLS={row['tls_full']} "
          f"CPU={row['cpu_busy_pct']}%" + (f" eBPF={row['ebpf_completed']}" if mode == "on" else ""), flush=True)
    return row


def save_reports(folder, rows, args):
    out = folder / "results.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    os.chmod(out, 0o600)
    lines = ["MTLS PERFORMANCE CAMPAIGN — SHAREABLE SUMMARY", "",
             f"Parameters: {args.threads} threads; {args.connections} connections; {args.duration}s per run; "
             "TLS 1.3; Connection: close; verified peer; zero resumed sessions required",
             "Result interpretation: primary throughput = OFF; observability distributions = ON, not directly interchangeable.",
             "", "Mode | Profile | N | Mean RPS | Std-dev RPS | Mean HTTP latency (ms) | Mean host CPU busy (%) | Mean observed handshake elapsed (ms)",
             "--- | --- | ---: | ---: | ---: | ---: | ---: | ---:"]
    for mode in ("off", "on"):
        for label, *_ in PROFILES:
            r = [x for x in rows if x["mode"] == mode and x["profile"] == label]
            if not r:
                continue
            mean = lambda key: statistics.mean(float(x[key]) for x in r if x.get(key) not in (None, ""))
            stdev = statistics.stdev([x["rps"] for x in r]) if len(r) >= 2 else 0.0
            on_mean = f"{mean('ebpf_full_mean_ms'):.3f}" if mode == "on" else "n/a"
            lines.append(f"{mode.upper()} | {label} | {len(r)} | {mean('rps'):.2f} | {stdev:.2f} | "
                         f"{mean('latency_mean_ms'):.2f} | {mean('cpu_busy_pct'):.2f} | {on_mean}")
    lines += ["", "Cautions: HTTP latency in wrk excludes TLS handshake setup. Observed eBPF elapsed begins at first server SSL_do_handshake call.",
              "Server CPU busy is a system-level utilization estimate, not exclusive Apache CPU time.",
              "Source logs stay local, contain internal hostnames, and MUST NOT be uploaded to public GitHub.",
              "No certificates, private keys, passwords, or tokens are read into outputs or copied by this script."]
    summary = folder / "SUMMARY.txt"
    summary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(summary, 0o600)
    print("\n" + "\n".join(lines))
    print("\nShare only: " + str(summary), flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", choices=("off", "on", "both"), default="off")
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--duration", type=int, default=120)
    ap.add_argument("--threads", type=int, default=8)
    ap.add_argument("--connections", type=int, default=50)
    ap.add_argument("--pause", type=int, default=10)
    ap.add_argument("--seed", type=int, default=20261118)
    ap.add_argument("--server", required=True)
    ap.add_argument("--web-host", required=True)
    ap.add_argument("--ssh-user", default="root")
    ap.add_argument("--wrk", required=True)
    ap.add_argument("--cert-dir", required=True)
    args = ap.parse_args()
    if args.runs < 1 or args.duration < 5 or args.threads < 1 or args.connections < args.threads or args.pause < 0:
        ap.error("Invalid run duration, count, concurrency, or pause")
    if os.geteuid() != 0:
        ap.error("Run on client as root")
    for p in [args.wrk] + [f"{args.cert_dir}/{name}" for profile in PROFILES for name in profile[2:5]]:
        if not Path(p).is_file():
            ap.error("Required local file missing: " + p)
    os.umask(0o077)
    folder = Path.home() / ("mtls-campaign-" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S"))
    folder.mkdir(mode=0o700)
    print("Results directory:", folder, flush=True)
    # Save only non-secret experiment parameters; never serialize environment/SSH settings.
    (folder / "run-parameters.json").write_text(json.dumps({
        "mode": args.mode, "runs": args.runs, "duration": args.duration,
        "threads": args.threads, "connections": args.connections,
        "pause": args.pause, "seed": args.seed}, indent=2) + "\n")
    rows = []
    exit_code = 0
    try:
        ssh(args, "systemctl is-active httpd >/dev/null && test -s /opt/tls-observer/tls_handshake.bt")
        for mode in (["off", "on"] if args.mode == "both" else [args.mode]):
            print("\n==== Starting", mode.upper(), "campaign ====", flush=True)
            change_state(args, mode)
            rng = random.Random(args.seed)
            for round_n in range(1, args.runs + 1):
                order = list(PROFILES)
                rng.shuffle(order)
                for k, profile in enumerate(order):
                    if k or round_n > 1:
                        time.sleep(args.pause)
                    row = do_run(args, mode, round_n, profile, folder)
                    rows.append(row)
                    save_reports(folder, rows, args)
    except (Exception, KeyboardInterrupt) as exc:
        print("\nCAMPAIGN INTERRUPTED:", exc, file=sys.stderr, flush=True)
        exit_code = 1
    finally:
        try:
            change_state(args, "on")
            print("Final exporter state: ACTIVE and observer READY", flush=True)
        except Exception as exc:
            print("WARNING: Could not restore exporter:", exc, file=sys.stderr)
            exit_code = 1
        try:
            save_reports(folder, rows, args)
        except Exception as exc:
            print("WARNING: report write failed:", exc, file=sys.stderr)
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    sys.exit(main())