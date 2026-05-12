"""Long-message handling: chunking + document attachment."""

import pytest


# --------------------------------------------------------------------------- #
# Telegram: send long messages
# --------------------------------------------------------------------------- #


class TestSendTelegramLong:
    def _configure(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
        import sleuth.config as cfg
        cfg._settings = None

    def test_short_text_one_send(self, monkeypatch, mocker):
        self._configure(monkeypatch)
        ok = mocker.Mock(status_code=200, text="ok")
        post = mocker.patch("sleuth.notify.telegram.httpx.post", return_value=ok)
        from sleuth.notify import send_telegram
        send_telegram("hello")
        assert post.call_count == 1
        # sendMessage endpoint
        url = post.call_args.args[0]
        assert "sendMessage" in url

    def test_medium_text_chunks_into_multiple_messages(self, monkeypatch, mocker):
        self._configure(monkeypatch)
        ok = mocker.Mock(status_code=200, text="ok")
        post = mocker.patch("sleuth.notify.telegram.httpx.post", return_value=ok)
        from sleuth.notify import send_telegram
        # ~8000 chars - should chunk into 2 messages (≤ 4096 each)
        text = "para.\n\n" + ("body para. " * 500)
        send_telegram(text)
        assert post.call_count >= 2
        for call in post.call_args_list:
            body = call.kwargs.get("json") or {}
            assert len(body.get("text", "")) <= 4096

    def test_very_long_text_uploads_as_document(self, monkeypatch, mocker):
        self._configure(monkeypatch)
        ok = mocker.Mock(status_code=200, text="ok")
        post = mocker.patch("sleuth.notify.telegram.httpx.post", return_value=ok)
        from sleuth.notify import send_telegram
        # ~20k chars — beyond the chunking threshold; should use sendDocument
        text = "z" * 20000
        send_telegram(text)
        # Last call should be sendDocument
        urls = [c.args[0] for c in post.call_args_list]
        assert any("sendDocument" in u for u in urls)


# --------------------------------------------------------------------------- #
# Telegram: explicit send_document
# --------------------------------------------------------------------------- #


class TestSendTelegramDocument:
    def _configure(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
        import sleuth.config as cfg
        cfg._settings = None

    def test_posts_to_send_document_endpoint(self, monkeypatch, mocker):
        self._configure(monkeypatch)
        ok = mocker.Mock(status_code=200, text="ok")
        post = mocker.patch("sleuth.notify.telegram.httpx.post", return_value=ok)
        from sleuth.notify.telegram import send_telegram_document
        send_telegram_document(b"hello world", filename="findings.md", caption="big one")
        assert post.call_count == 1
        url = post.call_args.args[0]
        assert "sendDocument" in url
        # multipart files in files= kwarg
        files = post.call_args.kwargs.get("files")
        assert files is not None
        # form fields
        data = post.call_args.kwargs.get("data") or {}
        assert data["chat_id"] == "42"
        assert data["caption"] == "big one"

    def test_4xx_raises(self, monkeypatch, mocker):
        self._configure(monkeypatch)
        bad = mocker.Mock(status_code=400, text="nope")
        mocker.patch("sleuth.notify.telegram.httpx.post", return_value=bad)
        from sleuth.notify.telegram import send_telegram_document, NotifyError
        with pytest.raises(NotifyError):
            send_telegram_document(b"x", filename="f.md")


# --------------------------------------------------------------------------- #
# Discord: long messages and file attachments
# --------------------------------------------------------------------------- #


class TestDiscordLong:
    def _configure(self, monkeypatch):
        monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.example/webhook")
        import sleuth.config as cfg
        cfg._settings = None

    def test_short_message_one_send(self, monkeypatch, mocker):
        self._configure(monkeypatch)
        ok = mocker.Mock(status_code=204, text="")
        post = mocker.patch("sleuth.notify.discord.httpx.post", return_value=ok)
        from sleuth.notify import send_discord
        send_discord("hello there")
        assert post.call_count == 1

    def test_medium_chunks(self, monkeypatch, mocker):
        self._configure(monkeypatch)
        ok = mocker.Mock(status_code=204, text="")
        post = mocker.patch("sleuth.notify.discord.httpx.post", return_value=ok)
        from sleuth.notify import send_discord
        text = ("body. " * 500)  # ~3000 chars > 2000 limit
        send_discord(text)
        assert post.call_count >= 2
        for call in post.call_args_list:
            payload = call.kwargs.get("json") or {}
            if "content" in payload:
                assert len(payload["content"]) <= 2000

    def test_very_long_uploads_as_file(self, monkeypatch, mocker):
        self._configure(monkeypatch)
        ok = mocker.Mock(status_code=204, text="")
        post = mocker.patch("sleuth.notify.discord.httpx.post", return_value=ok)
        from sleuth.notify import send_discord
        send_discord("z" * 15000)
        # Should have used multipart (files kwarg) somewhere
        used_multipart = any(c.kwargs.get("files") for c in post.call_args_list)
        assert used_multipart


class TestSendDiscordDocument:
    def _configure(self, monkeypatch):
        monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.example/webhook")
        import sleuth.config as cfg
        cfg._settings = None

    def test_posts_with_multipart(self, monkeypatch, mocker):
        self._configure(monkeypatch)
        ok = mocker.Mock(status_code=204, text="")
        post = mocker.patch("sleuth.notify.discord.httpx.post", return_value=ok)
        from sleuth.notify.discord import send_discord_document
        send_discord_document(b"contents", filename="run.md", caption="oh hi")
        assert post.call_count == 1
        files = post.call_args.kwargs.get("files")
        assert files is not None
        url = post.call_args.args[0]
        assert "webhook" in url


# --------------------------------------------------------------------------- #
# Runner-facing helper: notify_run_finished
# --------------------------------------------------------------------------- #


class TestNotifyRunFinished:
    """The high-level helper the runner calls. Sends the full body."""

    def test_telegram_short_sends_one_message(self, monkeypatch, mocker):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
        import sleuth.config as cfg
        cfg._settings = None
        ok = mocker.Mock(status_code=200, text="ok")
        mocker.patch("sleuth.notify.telegram.httpx.post", return_value=ok)

        from sleuth.notify import notify_run_finished
        delivered = notify_run_finished(
            provider="openai", model="gpt-5.5",
            prompt="what happened?",
            body="A short answer.",
        )
        assert "telegram" in delivered

    def test_long_body_uses_attachment(self, monkeypatch, mocker):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
        import sleuth.config as cfg
        cfg._settings = None
        ok = mocker.Mock(status_code=200, text="ok")
        post = mocker.patch("sleuth.notify.telegram.httpx.post", return_value=ok)

        from sleuth.notify import notify_run_finished
        delivered = notify_run_finished(
            provider="openai", model="gpt-5.5",
            prompt="big one",
            body="z" * 20000,
        )
        assert "telegram" in delivered
        # Some call must hit sendDocument
        urls = [c.args[0] for c in post.call_args_list]
        assert any("sendDocument" in u for u in urls)
