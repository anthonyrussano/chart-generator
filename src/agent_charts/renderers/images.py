"""SVG -> PNG.

The SVG is the source of truth; PNG is a raster of it. Native rasterizers are
tried first for a fast inner loop, with a container fallback so an agent on a
bare machine still gets an image.

Rasterizers ignore the `prefers-color-scheme` block in the stylesheet and
render the base rules, which are the light palette. For a dark PNG, render the
chart with `--theme dark`, which bakes the dark steps as the base rules.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from pathlib import Path

DEFAULT_IMAGE = "docker.io/minidocks/librsvg:latest"
RASTER_RUNTIMES = ("auto", "native", "container")
CONTAINER_ENGINES = ("auto", "docker", "podman")

# Tried in order. Each entry is (executable, argv builder).
_NATIVE_RASTERIZERS = (
    ("resvg", lambda src, dst, w: [
        "resvg", "--width", str(w), str(src), str(dst)
    ]),
    ("rsvg-convert", lambda src, dst, w: [
        "rsvg-convert", "--width", str(w), "--format", "png",
        "--output", str(dst), str(src),
    ]),
    ("inkscape", lambda src, dst, w: [
        "inkscape", str(src), "--export-type=png",
        f"--export-filename={dst}", f"--export-width={w}",
    ]),
    ("cairosvg", lambda src, dst, w: [
        "cairosvg", str(src), "-o", str(dst), "-W", str(w),
    ]),
)


class RasterError(RuntimeError):
    pass


def _run(cmd: list[str]) -> None:
    try:
        proc = subprocess.run(cmd, text=True, capture_output=True)
    except FileNotFoundError as exc:
        raise RasterError(
            "PNG rasterizer executable was not found\n"
            f"command: {shlex.join(cmd)}\n"
            f"executable: {cmd[0]}"
        ) from exc
    if proc.returncode != 0:
        raise RasterError(
            "PNG rasterizer command failed\n"
            f"command: {shlex.join(cmd)}\n"
            f"exit_code: {proc.returncode}\n"
            f"stdout:\n{proc.stdout}\n"
            f"stderr:\n{proc.stderr}"
        )


def _resolve_container_engine(requested: str) -> str:
    if requested not in CONTAINER_ENGINES:
        raise ValueError(
            f"Unsupported container engine '{requested}'. "
            f"Choose one of: {', '.join(CONTAINER_ENGINES)}."
        )
    if requested != "auto":
        if shutil.which(requested):
            return requested
        raise RasterError(f"Requested container engine '{requested}' was not found in PATH.")
    for candidate in ("docker", "podman"):
        if shutil.which(candidate):
            return candidate
    raise RasterError(
        "No container engine found in PATH. Install Docker or Podman, or install "
        "one of: resvg, rsvg-convert, inkscape, cairosvg, and use --raster-runtime native."
    )


def _host_user() -> tuple[int, int]:
    getuid = getattr(os, "getuid", None)
    getgid = getattr(os, "getgid", None)
    return (
        getuid() if getuid is not None else 1000,
        getgid() if getgid is not None else 1000,
    )


def find_native_rasterizer() -> str | None:
    for name, _ in _NATIVE_RASTERIZERS:
        if shutil.which(name):
            return name
    return None


def render_png(
    svg_path: Path,
    output_path: Path,
    *,
    width: int = 1440,
    runtime: str = "auto",
    container_engine: str = "auto",
    image: str = DEFAULT_IMAGE,
) -> Path:
    if runtime not in RASTER_RUNTIMES:
        raise ValueError(
            f"Unsupported raster runtime '{runtime}'. "
            f"Choose one of: {', '.join(RASTER_RUNTIMES)}."
        )

    svg_path = svg_path.resolve()
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    native = find_native_rasterizer()
    if runtime == "native":
        if native is None:
            raise RasterError(
                "No native rasterizer found. Install one of: resvg, rsvg-convert, "
                "inkscape, cairosvg - or use --raster-runtime container."
            )
        return _render_native(native, svg_path, output_path, width)

    if runtime == "auto" and native is not None:
        return _render_native(native, svg_path, output_path, width)

    return _render_container(svg_path, output_path, width, container_engine, image)


def _render_native(name: str, svg_path: Path, output_path: Path, width: int) -> Path:
    builder = dict(_NATIVE_RASTERIZERS)[name]
    _run(builder(svg_path, output_path, width))
    return output_path


def _render_container(
    svg_path: Path, output_path: Path, width: int, container_engine: str, image: str
) -> Path:
    engine = _resolve_container_engine(container_engine)
    # Mount the shared parent so both paths resolve inside the container.
    mount = _common_parent(svg_path, output_path)
    uid, gid = _host_user()
    cmd = [
        engine, "run", "--rm",
        "--user", f"{uid}:{gid}",
        "-v", f"{mount}:{mount}:rw",
        "-w", str(mount),
        image,
        "rsvg-convert", "--width", str(width), "--format", "png",
        "--output", str(output_path), str(svg_path),
    ]
    _run(cmd)
    return output_path


def _common_parent(*paths: Path) -> Path:
    parts = [p.parent.resolve().parts for p in paths]
    shared: list[str] = []
    for segments in zip(*parts):
        if len(set(segments)) != 1:
            break
        shared.append(segments[0])
    return Path(*shared) if shared else Path("/")
