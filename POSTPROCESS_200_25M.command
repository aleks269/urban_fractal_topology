#!/bin/bash
cd "$(dirname "$0")" || exit 1
exec bash scripts/postprocess_all_200_25m.sh /Volumes/aglikflash
