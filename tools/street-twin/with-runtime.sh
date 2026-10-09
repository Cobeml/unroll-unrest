#!/usr/bin/env bash
# Load runtime configuration without printing it or writing a repository env file.
set -euo pipefail
mapfile -t STREET_CONFIGS < <(find /config -maxdepth 1 -name '*.config' -type f | sort)
(( ${#STREET_CONFIGS[@]} == 1 )) || { echo 'Expected one team configuration.' >&2; exit 1; }
set -a
source "${STREET_CONFIGS[0]}"
set +a
export VSS_URL="$INGRESS_URL" VSS_USERNAME="$USERNAME" VSS_PASSWORD="$PASSWORD"
export KUBECONFIG="/config/${USERNAME}-k8s.yaml"
export STREETTWIN_SPATIAL_BUCKET="${STREETTWIN_SPATIAL_BUCKET:-$VASTDB_BUCKET}"
if [[ "$STREETTWIN_SPATIAL_BUCKET" == *-street-twin-spatial ]]; then
  export STREETTWIN_SPATIAL_PREFIX=''
else
  export STREETTWIN_SPATIAL_PREFIX='street-twin/spatial/'
fi
export STREETTWIN_S3_VERIFY="${STREETTWIN_S3_VERIFY:-false}"
export STREETTWIN_API_BASE="http://video-lab-${USERNAME}.cosmos.vastdata.com/app/"
exec "$@"
