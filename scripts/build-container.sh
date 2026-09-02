#!/usr/bin/env bash
# Build (or refresh) the chart-gen image.
set -euo pipefail

script_dir=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(CDPATH= cd -- "${script_dir}/.." && pwd)
image_name=${CHART_GEN_IMAGE:-chart-gen:local}
container_engine=${CONTAINER_ENGINE:-}

if [[ -z "${container_engine}" ]]; then
    if command -v docker >/dev/null 2>&1; then
        container_engine=docker
    elif command -v podman >/dev/null 2>&1; then
        container_engine=podman
    else
        echo "Neither Docker nor Podman is available." >&2
        exit 1
    fi
fi

echo "Building ${image_name} with ${container_engine}..."
exec "${container_engine}" build \
    --file "${repo_root}/Containerfile" \
    --tag "${image_name}" \
    "${repo_root}"
