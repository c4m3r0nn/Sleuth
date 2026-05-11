"""Cron command builder must not be vulnerable to CWD package-shadowing.

When cron fires, its CWD is the user's $HOME. If $HOME happens to contain
a directory whose name matches our package (e.g. ~/sleuth where the project
lives), then `python -m sleuth` sees that directory as a namespace package
and shadows the real installed `sleuth`. The fix is to invoke the venv's
console script directly, OR cd to a neutral directory first.
"""

from pathlib import Path

import pytest


def _expect_safe(cmd: str) -> None:
    """A safe command either uses an entry-point binary, or cds first."""
    uses_python_dash_m = "-m sleuth" in cmd or "-m\tsleuth" in cmd
    has_cd_prefix = cmd.lstrip().startswith("cd ")
    uses_entrypoint = "/bin/sleuth " in cmd
    if uses_python_dash_m and not has_cd_prefix:
        pytest.fail(f"unsafe cron command (CWD shadowing risk): {cmd!r}")
    # At least one safety guard must be in place:
    assert uses_entrypoint or has_cd_prefix, f"command lacks safety guard: {cmd!r}"


class TestExecCommand:
    def test_uses_safe_form(self):
        from sleuth.scheduler.cron import _command_for
        cmd = _command_for("abc123")
        _expect_safe(cmd)

    def test_includes_job_id(self):
        from sleuth.scheduler.cron import _command_for
        cmd = _command_for("abc123")
        assert "abc123" in cmd

    def test_redirects_to_log(self):
        from sleuth.scheduler.cron import _command_for
        cmd = _command_for("abc123")
        assert ">>" in cmd and "2>&1" in cmd

    def test_passes_exec_subcommand(self):
        from sleuth.scheduler.cron import _command_for
        cmd = _command_for("abc123")
        # whichever form, the _exec sub-command must be there
        assert "_exec" in cmd

    def test_prefers_entrypoint_when_present(self, monkeypatch, tmp_path):
        """If the venv has a `sleuth` script, use it (avoids -m issues)."""
        from sleuth.scheduler import cron as cron_mod
        fake_bin = tmp_path / "bin"
        fake_bin.mkdir()
        fake_sleuth = fake_bin / "sleuth"
        fake_sleuth.write_text("#!/bin/sh\necho fake\n")
        fake_sleuth.chmod(0o755)
        fake_python = fake_bin / "python"
        fake_python.write_text("#!/bin/sh\n")
        fake_python.chmod(0o755)
        monkeypatch.setattr(cron_mod, "sys", _make_fake_sys(str(fake_python)))
        cmd = cron_mod._command_for("xyz")
        assert str(fake_sleuth) in cmd
        assert "-m sleuth" not in cmd

    def test_falls_back_to_cd_when_no_entrypoint(self, monkeypatch, tmp_path):
        """When the venv lacks a `sleuth` script, fall back to `cd /tmp && python -m sleuth`."""
        from sleuth.scheduler import cron as cron_mod
        fake_bin = tmp_path / "bin"
        fake_bin.mkdir()
        # only a python binary, no sleuth script
        fake_python = fake_bin / "python"
        fake_python.write_text("#!/bin/sh\n")
        fake_python.chmod(0o755)
        monkeypatch.setattr(cron_mod, "sys", _make_fake_sys(str(fake_python)))
        cmd = cron_mod._command_for("xyz")
        assert cmd.lstrip().startswith("cd ")
        assert "-m sleuth" in cmd


class TestCatchupCommand:
    def test_uses_safe_form(self):
        from sleuth.scheduler.cron import _catchup_command
        cmd = _catchup_command()
        _expect_safe(cmd)

    def test_passes_catchup_subcommand(self):
        from sleuth.scheduler.cron import _catchup_command
        cmd = _catchup_command()
        assert "catchup" in cmd

    def test_passes_auto_flag(self):
        from sleuth.scheduler.cron import _catchup_command
        cmd = _catchup_command()
        assert "--auto" in cmd


def _make_fake_sys(executable_path: str):
    """Build a tiny stand-in for the `sys` module exposing only what we use."""
    class FakeSys:
        pass
    fs = FakeSys()
    fs.executable = executable_path
    return fs
