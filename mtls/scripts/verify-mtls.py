#!/usr/bin/env python3
"""Offline audit of the provided historical mTLS campaign.

Confirms internal consistency of published artifacts, NOT cryptographic
correctness, provenance of Prometheus/eBPF measurements, or source code of wrk.
"""
import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
PROFILES = {
    'mtls-classic': ('secp384r1', 'EC', 'client-ecdsa.crt'),
    'mtls-hybrid': ('X25519MLKEM768', 'EC', 'client-ecdsa.crt'),
    'mtls-pqc': ('X25519MLKEM768', 'ML-DSA-65', 'client-mldsa.crt'),
}


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def match(text, pattern, logfile):
    m = re.search(pattern, text, re.MULTILINE)
    require(m is not None, f'Missing pattern {pattern!r}: {logfile}')
    return m


def main():
    with (ROOT / 'results' / 'mtls-consolidated.csv').open(newline='') as f:
        rows = list(csv.DictReader(f))
    with (DATA / 'cpu-120s.csv').open(newline='') as f:
        cpu = list(csv.DictReader(f))
    with (ROOT / 'results' / 'runs.csv').open(newline='') as f:
        derived = list(csv.DictReader(f))
    require(len(rows) == len(cpu) == len(derived) == 9, 'Expected 9 rows in each input')
    keys = [(int(r['round']), r['profile']) for r in rows]
    expected = {(n,p) for n in (1,2,3) for p in PROFILES}
    require(set(keys) == expected and len(set(keys)) == 9, 'Missing or duplicate round/profile')
    cpu_keys = [(int(r['round']),r['profile']) for r in cpu]
    require(set(cpu_keys) == expected and len(set(cpu_keys))==9, 'CPU keys missing or duplicated')
    derived_by_key={(int(r['round']),r['profile']):r for r in derived}
    require(set(derived_by_key)==expected,'Derived rows missing or duplicated')
    summary_handshakes = 0
    for r in rows:
        key=(int(r['round']),r['profile'])
        log = DATA / r['logfile']
        require(log.is_file(), f'Missing {log}')
        t=log.read_text()
        require('Protocol: TLSv1.3' in t, f'Unexpected TLS version: {log}')
        require('8 threads and 50 connections' in t and 'Running 2m test' in t, f'Wrong load: {log}')
        expected_group,pubkey,cert=PROFILES[r['profile']]
        require(match(t,r'^Negotiated group: (.*)$',log).group(1)==expected_group, f'Wrong group: {log}')
        require(match(t,r'^Server public key: (.*)$',log).group(1)==pubkey, f'Wrong server public-key label: {log}')
        require(cert in t, f'Unexpected client certificate label: {log}')
        counts=match(t,r'^TLS handshake summary: full=(\d+) resumed=(\d+) total=(\d+)$',log)
        full,resumed,total=map(int,counts.groups())
        require(full==int(r['handshakes']) and total==full and resumed==0, f'Handshake mismatch: {log}')
        reqs=int(match(t,r'^\s*(\d+) requests in 2\.00m',log).group(1))
        require(0 <= full-reqs <= 100, f'Unexpected requests/handshakes gap: {log}')
        require('Socket errors:' not in t and 'Non-2xx or 3xx responses:' not in t, f'Review errors: {log}')
        for keyname in ('mean_ms','p50_ms','p95_ms','p99_ms'):
            require(float(r[keyname])>0,f'Invalid eBPF {keyname}: {log}')
        require(float(r['p50_ms'])<=float(r['p95_ms'])<=float(r['p99_ms']),f'Bad percentile order: {log}')
        dr=derived_by_key[key]
        require(int(dr['handshakes_full'])==full and int(dr['handshakes_resumed'])==0, f'Derived handshake mismatch: {log}')
        rps=float(match(t,r'^Requests/sec:\s+([\d.]+)',log).group(1))
        require(abs(float(dr['wrk_requests_per_sec'])-rps)<0.005,f'RPS mismatch: {log}')
        summary_handshakes+=full
    for r in cpu:
        reported=float(r['busy_pct'])
        components=sum(float(r[k]) for k in ('user_pct','system_pct','irq_pct'))
        require(abs(reported-components)<0.011, f'CPU component mismatch: {r}')
    figure_paths=list((ROOT/'figures/dark').glob('*.png'))
    require(len(figure_paths)==8, f'Expected 8 PNG figures, found {len(figure_paths)}')
    print(f'PASS: 9 logs / 3 profiles / 3 rounds; {summary_handshakes:,} recorded full handshakes; zero recorded resumptions; 8 figures')
    print('Scope: artifact consistency only. No independent eBPF counters, TLS authentication proofs, or original source traces in this package.')


if __name__ == '__main__':
    main()
