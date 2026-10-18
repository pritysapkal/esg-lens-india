#!/usr/bin/env bash
# Prepare the container's work folder: a copy of the host's data/raw (mounted read-only at
# /mnt/host_raw). cp -n never overwrites, so files the pipeline has already filed stay put and
# new files saved into the host inbox are picked up. Nothing is downloaded.
set -euo pipefail
WORK="${ESG_WORK:-/opt/airflow/esg_work}"
mkdir -p "$WORK/data/raw"
if [ -d /mnt/host_raw ]; then
  cp -rn /mnt/host_raw/. "$WORK/data/raw/"
fi
echo "work folder ready: $WORK ($(find "$WORK/data/raw" -name '*.xml' | wc -l) XBRL files)"
