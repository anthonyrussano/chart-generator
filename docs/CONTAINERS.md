# Containers

The container is the reproducible execution environment and the default for
agents. It is deliberately small: the renderer is pure Python and writes SVG
itself, so the only native dependency is `librsvg`, and only for PNG export.
There is no browser, no headless Chromium, and no JavaScript toolchain.

## Build and run

```bash
./scripts/build-container.sh
./scripts/run-container.sh chart --data examples/deploy-durations.csv --auto-form
./scripts/check-container.sh
```

The repo is mounted at `/workspace`, which is the container's working directory,
so relative paths work exactly as they do on the host and outputs land in your
checkout rather than inside the image.

## Engine selection

The wrappers prefer Docker and fall back to Podman. Choose explicitly:

```bash
CONTAINER_ENGINE=podman ./scripts/run-container.sh forms
CONTAINER_ENGINE=docker ./scripts/build-container.sh
```

Override the image tag with `CHART_GEN_IMAGE` (default `chart-gen:local`).

## Corporate certificate authorities

If dependency downloads fail with `invalid peer certificate: UnknownIssuer`,
pass a PEM CA bundle that already trusts your network's issuer:

```bash
CHART_GEN_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt ./scripts/build-container.sh
```

The wrapper supplies it as a build secret for dependency installation. The
bundle is not copied into the image and TLS verification remains enabled.
Docker's registry access and the OS package manager use their own trust setup;
this option applies to `uv` dependency downloads only. It requires an engine
with build-secret support.

## File ownership

The Docker path runs as `--user $(id -u):$(id -g)`; the Podman path uses
`--userns=keep-id`. Either way, files written to `output/` belong to you, not to
root.

## What check-container.sh verifies

1. Every module compiles
2. The whole test suite passes
3. `chart-gen --help` works
4. A real chart renders end to end
5. Every expected output file exists and is non-empty

This is the required check before finishing a change.
The image installs the locked `dev` extra so pytest is available to the check.

## PNG inside the container

`librsvg2-bin` is installed, so `--png` works natively:

```bash
./scripts/run-container.sh chart --data examples/deploy-durations.csv \
  --form bar --x service --y duration_seconds --png --out-dir output/
```

`chart-gen` can also shell out to a container *for rasterizing only*, when you
are running on the host without a rasterizer installed:

```bash
uv run chart-gen chart ... --png --raster-runtime container
```

## Falling back to the host

If no container engine is available, run on the host with `uv run`. Report the
fallback and the exact failure as a blind spot - the container path is what
makes the output reproducible, and a run that skipped it is a run with a known
gap.
