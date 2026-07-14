#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")"
exec bash scripts/run_all_200_25m_external.sh /Volumes/aglikflash
