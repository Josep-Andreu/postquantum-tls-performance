#!/usr/bin/env python3

import os
import signal
import subprocess
import sys
import threading
import time
import urllib.request

from prometheus_client import Counter, Gauge, Histogram, start_http_server

BPFTRACE = "/usr/bin/bpftrace"
BPFTRACE_SCRIPT = "/root/pqc-observability/bpftrace/tls_handshake.bt"
PROFILE_FILE = "/run/pqc-observability/profile"
LISTEN_PORT = 9101

APACHE_STATUS_URL = "http://127.0.0.1/server-status?auto"
APACHE_POLL_INTERVAL_SECONDS = 1

VALID_PROFILES = {
    "pqc-a1",
    "classic-a2",
    "pqc-b1",
    "pqc-c1",
    "classic-c2",
    "mtls-classic",
    "mtls-hybrid",
    "mtls-x25519",
    "mtls-pqc",
}

HANDSHAKE_CALLS = Counter(
    "tls_handshake_calls_total",
    "Calls to SSL_do_handshake observed by eBPF",
    ["profile", "result"],
)

HANDSHAKE_COMPLETED = Counter(
    "tls_handshakes_completed_total",
    "Successfully completed TLS handshakes observed by eBPF",
    ["profile"],
)

HANDSHAKE_DURATION = Histogram(
    "tls_handshake_duration_seconds",
    "Duration of successfully completed SSL_do_handshake calls",
    ["profile"],
    buckets=(
        0.00025,
        0.0005,
        0.001,
        0.002,
        0.003,
        0.004,
        0.005,
        0.006,
        0.007,
        0.008,
        0.010,
        0.012,
        0.015,
        0.020,
        0.030,
        0.050,
        0.075,
        0.100,
        0.150,
        0.250,
        float("inf"),
    ),
)

LAST_EVENT_TIMESTAMP = Gauge(
    "tls_observer_last_event_timestamp_seconds",
    "Unix timestamp of the most recent eBPF TLS event",
)

OBSERVER_UP = Gauge(
    "tls_observer_up",
    "Whether the bpftrace TLS observer process is running",
)

PARSE_ERRORS = Counter(
    "tls_observer_parse_errors_total",
    "Lines from bpftrace that could not be parsed as TLS events",
)

OBSERVER_RESTARTS = Counter(
    "tls_observer_restarts_total",
    "Number of times the bpftrace observer has been started",
)

ACTIVE_PROFILE = Gauge(
    "tls_observer_profile_info",
    "Currently selected experiment profile",
    ["profile"],
)

#
# Apache mod_status metrics
#

APACHE_STATUS_UP = Gauge(
    "apache_status_up",
    "Whether Apache mod_status is reachable",
)

APACHE_BUSY_WORKERS = Gauge(
    "apache_busy_workers",
    "Busy Apache workers",
)

APACHE_IDLE_WORKERS = Gauge(
    "apache_idle_workers",
    "Idle Apache workers",
)

APACHE_REQUESTS_PER_SECOND = Gauge(
    "apache_requests_per_second",
    "Apache requests per second reported by mod_status",
)

APACHE_BYTES_PER_SECOND = Gauge(
    "apache_bytes_per_second",
    "Apache bytes per second reported by mod_status",
)

APACHE_ACCESSES = Counter(
    "apache_accesses_total",
    "Total Apache requests reported by mod_status",
)

stop_event = threading.Event()
process = None
last_profile = None


def read_profile() -> str:
    try:
        with open(PROFILE_FILE, "r", encoding="utf-8") as profile_file:
            profile = profile_file.read().strip().lower()
    except OSError:
        return "unknown"

    if profile not in VALID_PROFILES:
        return "unknown"

    return profile


def update_profile_metric(profile: str) -> None:
    global last_profile

    if profile == last_profile:
        return

    if last_profile is not None:
        ACTIVE_PROFILE.labels(profile=last_profile).set(0)

    ACTIVE_PROFILE.labels(profile=profile).set(1)
    last_profile = profile


def handle_line(line: str) -> None:
    line = line.strip()

    if not line:
        return

    if (
        line.startswith("Attached")
        or line == "READY"
        or line == "STOPPED"
    ):
        print(f"bpftrace: {line}", flush=True)
        return

    if not line.startswith("HANDSHAKE "):
        PARSE_ERRORS.inc()
        print(
            f"Unparsed bpftrace output: {line}",
            file=sys.stderr,
            flush=True,
        )
        return

    try:
        fields = {}

        for item in line.split()[1:]:
            key, value = item.split("=", 1)
            fields[key] = value

        int(fields["pid"])
        int(fields["tid"])
        duration_ns = int(fields["duration_ns"])
        result = int(fields["result"])

    except (KeyError, ValueError):
        PARSE_ERRORS.inc()
        print(
            f"Invalid handshake event: {line}",
            file=sys.stderr,
            flush=True,
        )
        return

    profile = read_profile()
    update_profile_metric(profile)

    result_label = "completed" if result == 1 else "incomplete"

    HANDSHAKE_CALLS.labels(
        profile=profile,
        result=result_label,
    ).inc()

    if result == 1:
        duration_seconds = duration_ns / 1_000_000_000

        HANDSHAKE_COMPLETED.labels(
            profile=profile
        ).inc()

        HANDSHAKE_DURATION.labels(
            profile=profile
        ).observe(duration_seconds)

    LAST_EVENT_TIMESTAMP.set(time.time())


def parse_apache_status(body: str) -> dict[str, str]:
    values = {}

    for line in body.splitlines():
        if ":" not in line:
            continue

        key, value = line.split(":", 1)
        values[key.strip()] = value.strip()

    return values


def collect_apache_status() -> None:
    while not stop_event.is_set():
        try:
            with urllib.request.urlopen(
                APACHE_STATUS_URL,
                timeout=0.8,
            ) as response:
                body = response.read().decode("utf-8")

            values = parse_apache_status(body)

            APACHE_ACCESSES._value.set(
                float(values["Total Accesses"])
            )
            APACHE_BUSY_WORKERS.set(
                float(values["BusyWorkers"])
            )
            APACHE_IDLE_WORKERS.set(
                float(values["IdleWorkers"])
            )
            APACHE_REQUESTS_PER_SECOND.set(
                float(values["ReqPerSec"])
            )
            APACHE_BYTES_PER_SECOND.set(
                float(values["BytesPerSec"])
            )

            APACHE_STATUS_UP.set(1)

        except Exception as exc:
            APACHE_STATUS_UP.set(0)

            print(
                f"Apache mod_status collection failed: {exc}",
                file=sys.stderr,
                flush=True,
            )

        stop_event.wait(APACHE_POLL_INTERVAL_SECONDS)


def stop_handler(signum, frame) -> None:
    stop_event.set()

    if process is not None and process.poll() is None:
        process.send_signal(signal.SIGINT)


def run_observer() -> int:
    global process

    OBSERVER_RESTARTS.inc()

    process = subprocess.Popen(
        [
            "/usr/bin/stdbuf",
            "-oL",
            "-eL",
            BPFTRACE,
            BPFTRACE_SCRIPT,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env={
            **os.environ,
            "BPFTRACE_STRLEN": "128",
        },
    )

    OBSERVER_UP.set(1)

    assert process.stdout is not None

    try:
        for line in process.stdout:
            if stop_event.is_set():
                break

            handle_line(line)

    finally:
        OBSERVER_UP.set(0)

        if process.poll() is None:
            process.send_signal(signal.SIGINT)
            process.wait(timeout=10)

    return process.returncode


def main() -> int:
    signal.signal(signal.SIGTERM, stop_handler)
    signal.signal(signal.SIGINT, stop_handler)

    profile = read_profile()
    update_profile_metric(profile)

    start_http_server(LISTEN_PORT, addr="0.0.0.0")

    apache_thread = threading.Thread(
        target=collect_apache_status,
        name="apache-status-collector",
        daemon=True,
    )
    apache_thread.start()

    print(
        f"TLS eBPF exporter listening on port {LISTEN_PORT}",
        flush=True,
    )
    print(
        f"Active profile: {profile}",
        flush=True,
    )
    print(
        f"Apache status URL: {APACHE_STATUS_URL}",
        flush=True,
    )

    return run_observer()


if __name__ == "__main__":
    raise SystemExit(main())
