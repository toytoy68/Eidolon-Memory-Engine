# ==========================================================
# Projet      : Eidolon Memory Engine
# Organisation: Eidolon Core Technologies (ECT)
# Fichier     : core/preflight.py
# Description : Explicit pre-start filesystem and runtime check for a Memory Engine root.
# Standard    : Eidolon Presentation Standard v1
# ==========================================================

"""Explicit pre-start filesystem and runtime check for a Memory Engine root."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

from core.config import ENGINE_ROOT


class PreflightError(ValueError):
    """The configured root is not ready for a writer to start."""


def check_environment(root: Path, *, min_free_bytes: int = 1 << 30,
                      python_version: tuple[int, int] | None = None) -> dict:
    """Check the root explicitly, leaving no probe file behind."""
    version = python_version or sys.version_info[:2]
    if version < (3, 11):
        raise PreflightError("Python 3.11 or newer is required")
    configured = Path(root).absolute()
    try:
        real = configured.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise PreflightError(f"MEMORY_ENGINE_ROOT cannot be resolved: {configured}") from exc
    for component in (*reversed(configured.parents), configured):
        if component.is_symlink():
            raise PreflightError(
                f"MEMORY_ENGINE_ROOT uses symlink {component}; use real path {real}")
    if not configured.is_dir():
        raise PreflightError(f"MEMORY_ENGINE_ROOT is not a directory: {configured}")
    free = shutil.disk_usage(configured).free
    if free < min_free_bytes:
        raise PreflightError(
            f"insufficient free space at {real}: {free} bytes, need {min_free_bytes}")
    try:
        with tempfile.NamedTemporaryFile(dir=configured, prefix=".eidolon-preflight-", delete=True) as probe:
            probe.write(b"probe")
            probe.flush()
            os.fsync(probe.fileno())
    except OSError as exc:
        raise PreflightError(f"MEMORY_ENGINE_ROOT is not writable: {real}") from exc
    return {"python": f"{version[0]}.{version[1]}", "configured_root": str(configured),
            "realpath": str(real), "writable": True, "free_bytes": free,
            "required_free_bytes": min_free_bytes, "status": "OK"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ENGINE_ROOT,
                        help="MEMORY_ENGINE_ROOT (defaults to configured root)")
    parser.add_argument("--min-free-gib", type=float, default=1.0)
    args = parser.parse_args(argv)
    if args.min_free_gib < 0:
        parser.error("--min-free-gib must be nonnegative")
    try:
        result = check_environment(args.root, min_free_bytes=int(args.min_free_gib * (1 << 30)))
    except PreflightError as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
