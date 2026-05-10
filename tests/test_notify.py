"""Notifier behaviour. Outbound HTTP is mocked; we never hit the network."""

import pytest


# --------------------------------------------------------------------------- #
# Telegram
# --------------------------------------------------------------------------- #


class TestTelegram:
    def test_unconfigured_raises(self):
        from sleuth.notify import send_telegram, NotifyError, is_telegram_configured
        assert is_telegram_configured() is False
        with pytest.raises(NotifyError):
            send_telegram("hi")

    def test_configured_sends_payload(self, monkeypatch, mocker):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "abc:123")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
        # reset settings cache so the new env vars take effect
        import sleuth.config as cfg
        cfg._settings = None

        from sleuth.notify import send_telegram, is_telegram_configured
        assert is_telegram_configured() is True

        fake_resp = mocker.Mock(status_code=200, text="ok")
        post = mocker.patch("sleuth.notify.telegram.httpx.post", return_value=fake_resp)

        send_telegram("hello *world*")
        post.assert_called_once()
        url = post.call_args[0][0]
        body = post.call_args.kwargs["json"]
        assert "abc:123" in url
        assert body["chat_id"] == "42"
        assert body["text"] == "hello *world*"
        assert body["parse_mode"] == "Markdown"

    def test_4xx_raises(self, monkeypatch, mocker):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
        import sleuth.config as cfg
        cfg._settings = None

        from sleuth.notify import send_telegram, NotifyError
        bad = mocker.Mock(status_code=403, text="forbidden")
        mocker.patch("sleuth.notify.telegram.httpx.post", return_value=bad)
        with pytest.raises(NotifyError):
            send_telegram("hi")


# --------------------------------------------------------------------------- #
# Discord
# --------------------------------------------------------------------------- #


class TestDiscord:
    def test_unconfigured_raises(self):
        from sleuth.notify import send_discord, NotifyError, is_discord_configured
        assert is_discord_configured() is False
        with pytest.raises(NotifyError):
            send_discord("hi")

    def test_configured_sends_payload(self, monkeypatch, mocker):
        monkeypatch.setenv(
            "DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/abc/xyz"
        )
        import sleuth.config as cfg
        cfg._settings = None

        from sleuth.notify import send_discord, is_discord_configured
        assert is_discord_configured() is True

        fake_resp = mocker.Mock(status_code=204, text="")
        post = mocker.patch("sleuth.notify.discord.httpx.post", return_value=fake_resp)
        send_discord("hello there")
        post.assert_called_once()
        url = post.call_args[0][0]
        body = post.call_args.kwargs["json"]
        assert url == "https://discord.com/api/webhooks/abc/xyz"
        assert body["content"] == "hello there"

    def test_handles_204_no_content(self, monkeypatch, mocker):
        """Discord returns 204 on success; we should treat that as fine."""
        monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://x")
        import sleuth.config as cfg
        cfg._settings = None
        from sleuth.notify import send_discord
        ok = mocker.Mock(status_code=204, text="")
        mocker.patch("sleuth.notify.discord.httpx.post", return_value=ok)
        send_discord("ok")  # no raise

    def test_5xx_raises(self, monkeypatch, mocker):
        monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://x")
        import sleuth.config as cfg
        cfg._settings = None
        from sleuth.notify import send_discord, NotifyError
        bad = mocker.Mock(status_code=500, text="boom")
        mocker.patch("sleuth.notify.discord.httpx.post", return_value=bad)
        with pytest.raises(NotifyError):
            send_discord("hi")


# --------------------------------------------------------------------------- #
# notify_all (the runner-facing helper)
# --------------------------------------------------------------------------- #


class TestNotifyAll:
    def test_skips_unconfigured(self, mocker):
        """If neither channel is set, notify_all does nothing and doesn't raise."""
        from sleuth.notify import notify_all
        notify_all("hello", channels=("telegram", "discord"))

    def test_routes_to_configured(self, monkeypatch, mocker):
        monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://x")
        import sleuth.config as cfg
        cfg._settings = None

        ok = mocker.Mock(status_code=204, text="")
        post = mocker.patch("sleuth.notify.discord.httpx.post", return_value=ok)

        from sleuth.notify import notify_all
        notify_all("hi", channels=("telegram", "discord"))
        # Telegram is unconfigured -> skipped, Discord is configured -> called.
        post.assert_called_once()
