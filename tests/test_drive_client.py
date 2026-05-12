"""Selection of which OAuth client to use for Drive.

Order of preference:
  1. env vars SLEUTH_GOOGLE_CLIENT_ID + SLEUTH_GOOGLE_CLIENT_SECRET
  2. module-level constants in sleuth.storage.drive_client (set by maintainer)
  3. legacy GDRIVE_CLIENT_SECRET_PATH (custom per-user JSON file)
  4. raise NoClientConfigured
"""

import json
from pathlib import Path

import pytest


class TestEnvVarSource:
    def test_env_vars_take_precedence(self, monkeypatch):
        monkeypatch.setenv("SLEUTH_GOOGLE_CLIENT_ID", "env-id")
        monkeypatch.setenv("SLEUTH_GOOGLE_CLIENT_SECRET", "env-secret")
        # reset settings singleton so the new env vars are seen
        import sleuth.config as cfg
        cfg._settings = None

        from sleuth.storage.drive_client import resolve_client
        info = resolve_client()
        assert info.client_id == "env-id"
        assert info.client_secret == "env-secret"
        assert info.source == "env"

    def test_values_from_dotenv_file(self, monkeypatch, tmp_path):
        """Values in .env must be picked up even if they're NOT in os.environ.

        Pydantic-settings loads the .env file into the Settings object but
        doesn't push the keys back into os.environ. The resolver has to read
        from Settings, not from os.environ directly.
        """
        env_file = tmp_path / "dotenv"
        env_file.write_text(
            "SLEUTH_GOOGLE_CLIENT_ID=dotenv-id\n"
            "SLEUTH_GOOGLE_CLIENT_SECRET=dotenv-secret\n"
        )
        # Override the autouse-fixture's "nope.env" pointer with our file.
        import sleuth.config as cfg
        monkeypatch.setitem(cfg.Settings.model_config, "env_file", str(env_file))
        cfg._settings = None

        # Make sure os.environ does NOT have these — that's the whole point.
        assert "SLEUTH_GOOGLE_CLIENT_ID" not in __import__("os").environ
        assert "SLEUTH_GOOGLE_CLIENT_SECRET" not in __import__("os").environ

        from sleuth.storage.drive_client import resolve_client
        info = resolve_client()
        assert info.client_id == "dotenv-id"
        assert info.client_secret == "dotenv-secret"
        assert info.source == "env"

    def test_partial_env_skipped(self, monkeypatch, tmp_path):
        """Only id but no secret -> ignore env and fall through."""
        monkeypatch.setenv("SLEUTH_GOOGLE_CLIENT_ID", "only-id")
        # no secret
        import sleuth.config as cfg
        cfg._settings = None

        from sleuth.storage.drive_client import resolve_client, NoClientConfigured
        with pytest.raises(NoClientConfigured):
            resolve_client()


class TestBuiltinSource:
    def test_builtin_used_when_set(self, monkeypatch):
        # ensure env doesn't shadow
        import sleuth.config as cfg
        cfg._settings = None
        from sleuth.storage import drive_client as dc
        monkeypatch.setattr(dc, "BUILTIN_CLIENT_ID", "built-id")
        monkeypatch.setattr(dc, "BUILTIN_CLIENT_SECRET", "built-secret")

        info = dc.resolve_client()
        assert info.client_id == "built-id"
        assert info.source == "builtin"


class TestCustomFileSource:
    def test_user_file_used_when_no_builtin(self, monkeypatch, tmp_path):
        cs = tmp_path / "client_secret.json"
        cs.write_text(json.dumps({"installed": {
            "client_id": "file-id",
            "client_secret": "file-sec",
        }}))
        monkeypatch.setenv("GDRIVE_CLIENT_SECRET_PATH", str(cs))
        import sleuth.config as cfg
        cfg._settings = None

        from sleuth.storage.drive_client import resolve_client
        info = resolve_client()
        assert info.client_id == "file-id"
        assert info.client_secret == "file-sec"
        assert info.source == "file"

    def test_explicit_path_arg_wins_over_env(self, monkeypatch, tmp_path):
        env_file = tmp_path / "env.json"
        env_file.write_text(json.dumps({"installed": {
            "client_id": "env-file-id", "client_secret": "env-sec",
        }}))
        arg_file = tmp_path / "arg.json"
        arg_file.write_text(json.dumps({"installed": {
            "client_id": "arg-file-id", "client_secret": "arg-sec",
        }}))
        monkeypatch.setenv("GDRIVE_CLIENT_SECRET_PATH", str(env_file))
        import sleuth.config as cfg
        cfg._settings = None

        from sleuth.storage.drive_client import resolve_client
        info = resolve_client(explicit_path=arg_file)
        assert info.client_id == "arg-file-id"
        assert info.source == "file"


class TestNoClient:
    def test_raises_when_nothing_set(self):
        from sleuth.storage.drive_client import resolve_client, NoClientConfigured
        with pytest.raises(NoClientConfigured):
            resolve_client()


class TestStatus:
    def test_describe_includes_source(self, monkeypatch):
        monkeypatch.setenv("SLEUTH_GOOGLE_CLIENT_ID", "env-id")
        monkeypatch.setenv("SLEUTH_GOOGLE_CLIENT_SECRET", "env-secret")
        import sleuth.config as cfg
        cfg._settings = None
        from sleuth.storage.drive_client import describe_client
        line = describe_client()
        assert "env" in line.lower()
        # don't leak the secret
        assert "env-secret" not in line
        # id is OK to show (it's not really secret for installed apps)
        assert "env-id" in line

    def test_describe_when_unconfigured(self):
        from sleuth.storage.drive_client import describe_client
        line = describe_client()
        assert "not configured" in line.lower() or "no client" in line.lower()
