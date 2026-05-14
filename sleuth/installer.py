"""Helpers for making sleuth feel installed: shim symlink + system checks.

The goal: `sleuth` should work from any directory without `source .venv/bin/activate`,
and we should be able to tell the user clearly whether cron is up and willing
to fire their scheduled jobs.

All helpers are testable in isolation. Side-effecting commands accept their
target paths as parameters so tests can use tmp dirs.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional


# --------------------------------------------------------------------------- #
# paths
# --------------------------------------------------------------------------- #


def default_shim_path() -> Path:
    """Where we install the `sleuth` symlink. ~/.local/bin is on PATH on Pi OS
    Bookworm out of the box, and on modern macOS too."""
    return Path.home() / ".local" / "bin" / "sleuth"


def sleuth_binary_path() -> Optional[Path]:
    """Where the venv's installed `sleuth` console script lives."""
    candidate = Path(sys.executable).parent / "sleuth"
    if candidate.exists() and candidate.is_file():
        return candidate
    return None


def local_bin_on_path() -> bool:
    """True if ~/.local/bin appears in $PATH."""
    home_bin = str(Path.home() / ".local" / "bin")
    return home_bin in (os.environ.get("PATH", "") or "").split(os.pathsep)


# --------------------------------------------------------------------------- #
# shim installation
# --------------------------------------------------------------------------- #


def install_shim(
    *,
    shim_path: Optional[Path] = None,
    source: Optional[Path] = None,
    force: bool = False,
) -> Path:
    """Create a symlink at `shim_path` -> `source` so `sleuth` is on PATH.

    Idempotent: re-running with the same `source` is a no-op. Raises
    FileExistsError if a different target is already there, unless
    `force=True` (which replaces it).
    """
    if shim_path is None:
        shim_path = default_shim_path()
    if source is None:
        source = sleuth_binary_path()
    if source is None:
        raise FileNotFoundError(
            "no `sleuth` binary in this venv's bin dir — is sleuth installed (`pip install -e .`)?"
        )
    source = Path(source)
    if not source.exists():
        raise FileNotFoundError(f"source binary does not exist: {source}")

    shim_path.parent.mkdir(parents=True, exist_ok=True)

    if shim_path.is_symlink() or shim_path.exists():
        # Already pointing at the right place? Done.
        try:
            same = shim_path.resolve() == source.resolve()
        except OSError:
            same = False
        if same:
            return shim_path
        if not force:
            raise FileExistsError(
                f"{shim_path} already exists; pass force=True to overwrite."
            )
        shim_path.unlink()

    shim_path.symlink_to(source)
    return shim_path


# --------------------------------------------------------------------------- #
# system checks
# --------------------------------------------------------------------------- #


def cron_status() -> str:
    """Best-effort check for the system cron daemon.

    Returns one of: 'active', 'inactive', 'activating', 'failed', or 'unknown'
    (when systemctl isn't available — e.g. macOS).
    """
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "cron"],
            capture_output=True, text=True, timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return "unknown"
    out = (result.stdout or "").strip()
    if out in {"active", "inactive", "activating", "failed"}:
        return out
    return "unknown"


def has_cron_binary() -> bool:
    """True if `cron` is in $PATH at all (i.e. the package is installed)."""
    import shutil
    return shutil.which("cron") is not None or Path("/usr/sbin/cron").exists()
