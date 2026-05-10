"""Setup wizard helpers (the parts we can test without prompts)."""

from pathlib import Path

import pytest


class TestWriteEnvFile:
    def test_writes_simple_pairs(self, tmp_path):
        from sleuth.setup_wizard import write_env_file
        target = tmp_path / ".env"
        write_env_file(target, {"OPENAI_API_KEY": "sk-abc", "SLEUTH_DEFAULT_MODEL": "gpt-5.5"})
        assert target.exists()
        text = target.read_text()
        assert "OPENAI_API_KEY=sk-abc" in text
        assert "SLEUTH_DEFAULT_MODEL=gpt-5.5" in text

    def test_quotes_values_with_spaces(self, tmp_path):
        from sleuth.setup_wizard import write_env_file
        target = tmp_path / ".env"
        write_env_file(target, {"FOO": "hello world"})
        text = target.read_text()
        # Must round-trip via dotenv-style quoting.
        assert 'FOO="hello world"' in text

    def test_skips_empty_values(self, tmp_path):
        from sleuth.setup_wizard import write_env_file
        target = tmp_path / ".env"
        write_env_file(target, {"FILLED": "x", "EMPTY": "", "NONE": None})
        text = target.read_text()
        assert "FILLED=x" in text
        assert "EMPTY=" not in text
        assert "NONE=" not in text

    def test_backs_up_existing(self, tmp_path):
        from sleuth.setup_wizard import write_env_file
        target = tmp_path / ".env"
        target.write_text("OLD=value\n")
        backup = write_env_file(target, {"NEW": "value"})
        assert backup is not None
        assert backup.exists()
        assert "OLD=value" in backup.read_text()
        # New file replaces, doesn't append.
        new = target.read_text()
        assert "OLD" not in new
        assert "NEW=value" in new

    def test_no_backup_when_no_existing(self, tmp_path):
        from sleuth.setup_wizard import write_env_file
        target = tmp_path / ".env"
        backup = write_env_file(target, {"X": "1"})
        assert backup is None

    def test_writes_section_headers(self, tmp_path):
        """The wizard should produce a tidy file with comment headers."""
        from sleuth.setup_wizard import write_env_file
        target = tmp_path / ".env"
        write_env_file(
            target,
            {"OPENAI_API_KEY": "sk-1", "TELEGRAM_BOT_TOKEN": "t"},
            sections=[
                ("providers", ["OPENAI_API_KEY"]),
                ("notifications", ["TELEGRAM_BOT_TOKEN"]),
            ],
        )
        text = target.read_text()
        assert "# providers" in text
        assert "# notifications" in text
        # The pair after each header.
        prov_idx = text.index("# providers")
        notif_idx = text.index("# notifications")
        oai_idx = text.index("OPENAI_API_KEY")
        tg_idx = text.index("TELEGRAM_BOT_TOKEN")
        assert prov_idx < oai_idx < notif_idx < tg_idx


class TestPlanFromAnswers:
    """A pure function that converts wizard answers into the env-vars dict."""

    def test_basic_openai_only(self):
        from sleuth.setup_wizard import plan_env_from_answers
        plan = plan_env_from_answers(
            providers={"openai": "sk-abc"},
            default_provider="openai",
            default_model="gpt-5.5",
        )
        assert plan["OPENAI_API_KEY"] == "sk-abc"
        assert plan["SLEUTH_DEFAULT_PROVIDER"] == "openai"
        assert plan["SLEUTH_DEFAULT_MODEL"] == "gpt-5.5"

    def test_includes_telegram_when_given(self):
        from sleuth.setup_wizard import plan_env_from_answers
        plan = plan_env_from_answers(
            providers={"openai": "sk"},
            default_provider="openai",
            default_model="gpt-5.5",
            telegram_token="123:abc",
            telegram_chat_id="42",
        )
        assert plan["TELEGRAM_BOT_TOKEN"] == "123:abc"
        assert plan["TELEGRAM_CHAT_ID"] == "42"

    def test_includes_discord_when_given(self):
        from sleuth.setup_wizard import plan_env_from_answers
        plan = plan_env_from_answers(
            providers={"anthropic": "ant-key"},
            default_provider="anthropic",
            default_model="claude-opus-4-7",
            discord_webhook="https://discord/x",
        )
        assert plan["DISCORD_WEBHOOK_URL"] == "https://discord/x"

    def test_omits_unconfigured_keys(self):
        from sleuth.setup_wizard import plan_env_from_answers
        plan = plan_env_from_answers(
            providers={"openai": "sk"},
            default_provider="openai",
            default_model="gpt-5.5",
        )
        assert "ANTHROPIC_API_KEY" not in plan
        assert "GOOGLE_API_KEY" not in plan
        assert "TELEGRAM_BOT_TOKEN" not in plan
        assert "DISCORD_WEBHOOK_URL" not in plan
