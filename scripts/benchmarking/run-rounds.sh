#!/bin/bash
set -euo pipefail

# Usage: WEB=web.lab.example.com WRK=/path/to/wrk ./run-round.sh 1
# Run on the load-generation client. SSH access to the web server is required.
ROUND="${1:?Usage: run-round.sh ROUND (1-5)}"
WEB="${WEB:-web.lab.example.com}"
WRK="${WRK:-/usr/local/src/wrk}"
BASE="${BASE:-$HOME/pqc-benchmark-results/120s-t8}"
OPENSSL_MLDSA65="${OPENSSL_MLDSA65:-$HOME/openssl-mldsa.cnf}"
OPENSSL_MLDSA87_MLKEM1024="${OPENSSL_MLDSA87_MLKEM1024:-$HOME/openssl-mldsa87-mlkem1024.cnf}"
SSH_TARGET="${SSH_TARGET:-root@$WEB}"
OUT="$BASE/round${ROUND}"

# Validate round and required local files before creating output directories.
case "$ROUND" in 1|2|3|4|5) ;; *) echo "Round must be 1-5" >&2; exit 1 ;; esac
[[ -x "$WRK/wrk" && -f "$WRK/close.lua" ]] || {
  echo "Missing wrk executable or close.lua in $WRK" >&2; exit 1;
}
for conf in "$OPENSSL_MLDSA65" "$OPENSSL_MLDSA87_MLKEM1024"; do
  [[ -f "$conf" ]] || { echo "Missing OpenSSL configuration: $conf" >&2; exit 1; }
done
mkdir -p "$OUT"
cd "$WRK"

case "$ROUND" in
  1) ORDER=(classic-c2 pqc-a1 pqc-b1 classic-a2 pqc-c1) ;;
  2) ORDER=(pqc-b1 pqc-c1 classic-a2 classic-c2 pqc-a1) ;;
  3) ORDER=(classic-a2 classic-c2 pqc-a1 pqc-c1 pqc-b1) ;;
  4) ORDER=(pqc-c1 pqc-b1 classic-c2 pqc-a1 classic-a2) ;;
  5) ORDER=(pqc-a1 classic-a2 pqc-c1 pqc-b1 classic-c2) ;;
  *) echo "Round must be 1-5"; exit 1 ;;
esac

for i in "${!ORDER[@]}"; do
  PROFILE="${ORDER[$i]}"

  case "$PROFILE" in
    classic-a2)
      PORT=8443
      CONF=""
      ;;
    classic-c2)
      PORT=9443
      CONF=""
      ;;
    pqc-a1)
      PORT=10443
      CONF="$OPENSSL_MLDSA65"
      ;;
    pqc-b1)
      PORT=11443
      CONF="$OPENSSL_MLDSA65"
      ;;
    pqc-c1)
      PORT=12443
      CONF="$OPENSSL_MLDSA87_MLKEM1024"
      ;;
  esac

  LOG="$OUT/${PROFILE}-wrk.log"

  if [[ -e "$LOG" ]]; then
    echo "ERROR: $LOG already exists; refusing to overwrite"
    exit 1
  fi

  echo "=========================================="
  echo "Round $ROUND - $PROFILE - port $PORT"
  echo "=========================================="

  ssh -o BatchMode=yes -o ConnectTimeout=5 "$SSH_TARGET" \
    "echo '$PROFILE' > /run/pqc-observability/profile && \
     systemctl restart pqc-tls-exporter && \
     systemctl is-active --quiet pqc-tls-exporter"

  echo "Waiting 60 seconds..."
  sleep 60

  {
    date -u '+START UTC: %Y-%m-%dT%H:%M:%SZ'

    if [[ -n "$CONF" ]]; then
      OPENSSL_CONF="$CONF" \
        ./wrk -t8 -c50 -d120s --latency -s close.lua \
        "https://$WEB:$PORT/"
    else
      ./wrk -t8 -c50 -d120s --latency -s close.lua \
        "https://$WEB:$PORT/"
    fi

    date -u '+END UTC: %Y-%m-%dT%H:%M:%SZ'
  } | tee "$LOG"

done

echo "Round $ROUND completed."
