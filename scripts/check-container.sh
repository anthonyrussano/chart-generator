#!/usr/bin/env bash
# The required pre-finish check: tests, compilation, CLI surface, and a smoke
# render, all inside the container.
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

run_in_container() {
    case "${container_engine}" in
        docker)
            docker run --rm --entrypoint "$1" \
                --user "$(id -u):$(id -g)" \
                --volume "${repo_root}:/workspace" \
                "${image_name}" "${@:2}"
            ;;
        podman)
            podman run --rm --entrypoint "$1" \
                --userns=keep-id \
                --volume "${repo_root}:/workspace:Z" \
                "${image_name}" "${@:2}"
            ;;
    esac
}

echo "==> compile check"
run_in_container python -m compileall -q /app/src

echo "==> test suite"
run_in_container python -m pytest /workspace/tests -q

echo "==> CLI help"
run_in_container chart-gen --help >/dev/null

echo "==> smoke render"
run_in_container chart-gen \
    chart --data examples/deploy-durations.csv --auto-form \
    --out-dir output/container-smoke --name smoke

echo "==> verifying outputs"
for suffix in svg chart.json md blindspots.json blindspots.md; do
    path="${repo_root}/output/container-smoke/smoke.${suffix}"
    [[ -s "${path}" ]] || { echo "missing or empty: ${path}" >&2; exit 1; }
    echo "    ok  ${path}"
done

echo "All container checks passed."
