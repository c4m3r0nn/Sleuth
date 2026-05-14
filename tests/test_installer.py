"""Shim installer + system checks.

install_shim creates a symlink at ~/.local/bin/sleuth pointing at the venv's
own `sleuth` binary. Once that's there, the command works from any directory
without `source .venv/bin/activate`.
"""

from pathlib import Path
import os

import pytest


# --------------------------------------------------------------------------- #
# install_shim — symlink creation
# --------------------------------------------------------------------------- #


class TestInstallShim:
    def _fake_venv_binary(self, tmp_path: Path) -> Path:
        b = tmp_path / "venv" / "bin" / "sleuth"
        b.parent.mkdir(parents=True)
        b.write_text("#!/bin/sh\necho hi\n")
        b.chmod(0o755)
        return b

    def test_creates_symlink_when_none_exists(self, tmp_path):
        from sleuth.installer import install_shim
        source = self._fake_venv_binary(tmp_path)
        shim = tmp_path / "user" / "local" / "bin" / "sleuth"

        result = install_shim(shim_path=shim, source=source)
        assert result == shim
        assert shim.is_symlink()
        assert shim.resolve() == source.resolve()

    def test_creates_parent_dir(self, tmp_path):
        from sleuth.installer import install_shim
        source = self._fake_venv_binary(tmp_path)
        shim = tmp_path / "deep" / "nested" / "bin" / "sleuth"
        install_shim(shim_path=shim, source=source)
        assert shim.parent.exists()

    def test_idempotent_when_already_correct(self, tmp_path):
        from sleuth.installer import install_shim
        source = self._fake_venv_binary(tmp_path)
        shim = tmp_path / "bin" / "sleuth"
        install_shim(shim_path=shim, source=source)
        # Run again — should not raise
        install_shim(shim_path=shim, source=source)
        assert shim.is_symlink()
        assert shim.resolve() == source.resolve()

    def test_raises_when_shim_points_elsewhere(self, tmp_path):
        from sleuth.installer import install_shim
        source = self._fake_venv_binary(tmp_path)
        shim = tmp_path / "bin" / "sleuth"
        # Pre-existing shim pointing to a different file
        other = tmp_path / "other"
        other.write_text("x")
        shim.parent.mkdir(parents=True)
        shim.symlink_to(other)

        with pytest.raises(FileExistsError):
            install_shim(shim_path=shim, source=source)

    def test_force_overwrites_existing(self, tmp_path):
        from sleuth.installer import install_shim
        source = self._fake_venv_binary(tmp_path)
        other = tmp_path / "other"; other.write_text("x")
        shim = tmp_path / "bin" / "sleuth"
        shim.parent.mkdir(parents=True)
        shim.symlink_to(other)

        install_shim(shim_path=shim, source=source, force=True)
        assert shim.resolve() == source.resolve()

    def test_raises_when_source_missing(self, tmp_path):
        from sleuth.installer import install_shim
        nope = tmp_path / "venv" / "bin" / "sleuth"  # doesn't exist
        shim = tmp_path / "bin" / "sleuth"
        with pytest.raises(FileNotFoundError):
            install_shim(shim_path=shim, source=nope)


# --------------------------------------------------------------------------- #
# Default paths — small sanity, no side effects
# --------------------------------------------------------------------------- #


class TestPathHelpers:
    def test_default_shim_under_home_local_bin(self):
        from sleuth.installer import default_shim_path
        p = default_shim_path()
        assert p.name == "sleuth"
        assert str(p).endswith(str(Path(".local") / "bin" / "sleuth"))

    def test_sleuth_binary_path_under_venv_bin(self):
        from sleuth.installer import sleuth_binary_path
        p = sleuth_binary_path()
        if p is not None:
            assert p.name == "sleuth"
            assert p.parent.name == "bin"

    def test_local_bin_on_path_returns_bool(self, monkeypatch):
        from sleuth.installer import local_bin_on_path
        monkeypatch.setenv("PATH", "/usr/bin:/bin")
        assert local_bin_on_path() is False
        home_bin = str(Path.home() / ".local" / "bin")
        monkeypatch.setenv("PATH", f"{home_bin}:/usr/bin")
        assert local_bin_on_path() is True


# --------------------------------------------------------------------------- #
# Cron daemon detection
# --------------------------------------------------------------------------- #


class TestCronStatus:
    def test_returns_known_state(self, mocker):
        """When systemctl reports 'active', we report 'active'."""
        from sleuth.installer import cron_status
        result_mock = mocker.Mock(stdout="active\n", returncode=0)
        mocker.patch("sleuth.installer.subprocess.run", return_value=result_mock)
        assert cron_status() == "active"

    def test_returns_inactive(self, mocker):
        from sleuth.installer import cron_status
        result_mock = mocker.Mock(stdout="inactive\n", returncode=3)
        mocker.patch("sleuth.installer.subprocess.run", return_value=result_mock)
        assert cron_status() == "inactive"

    def test_falls_back_when_no_systemctl(self, mocker):
        from sleuth.installer import cron_status
        mocker.patch(
            "sleuth.installer.subprocess.run",
            side_effect=FileNotFoundError("no systemctl"),
        )
        # On macOS there is no systemctl - we return 'unknown' rather than crash.
        assert cron_status() == "unknown"

    def test_handles_timeout(self, mocker):
        from sleuth.installer import cron_status
        import subprocess
        mocker.patch(
            "sleuth.installer.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="systemctl", timeout=5),
        )
        assert cron_status() == "unknown"
