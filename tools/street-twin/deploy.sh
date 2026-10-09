#!/usr/bin/env bash
# Runtime credentials stay outside Git and are passed to kubectl through stdin.
set -euo pipefail
mapfile -t STREET_CONFIGS < <(find /config -maxdepth 1 -type f -name '*.config' | sort)
if (( ${#STREET_CONFIGS[@]} != 1 )); then
  echo 'Expected one team configuration in /config.' >&2
  exit 1
fi
set -a
source "${STREET_CONFIGS[0]}"
set +a
export VSS_URL="$INGRESS_URL" VSS_USERNAME="$USERNAME" VSS_PASSWORD="$PASSWORD"
export KUBECONFIG="/config/${USERNAME}-k8s.yaml"
cd "$(dirname "$0")"
exec python3 deploy.py
