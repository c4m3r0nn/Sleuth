"""REPL line parser & meta-command detection."""

import pytest


class TestParseLine:
    def test_simple(self):
        from sleuth.repl import parse_line
        assert parse_line("ask hello") == ["ask", "hello"]

    def test_quoted_string(self):
        from sleuth.repl import parse_line
        assert parse_line('ask "hello world"') == ["ask", "hello world"]

    def test_single_quotes(self):
        from sleuth.repl import parse_line
        assert parse_line("ask 'hello world'") == ["ask", "hello world"]

    def test_empty(self):
        from sleuth.repl import parse_line
        assert parse_line("") == []
        assert parse_line("    ") == []

    def test_comment(self):
        from sleuth.repl import parse_line
        assert parse_line("# this is a note") == []
        assert parse_line("   # also a note") == []

    def test_multi_args_with_flags(self):
        from sleuth.repl import parse_line
        out = parse_line("jobs schedule abc --daily 09:00")
        assert out == ["jobs", "schedule", "abc", "--daily", "09:00"]

    def test_strips_leading_sleuth_prefix(self):
        """Pasting 'sleuth ask hi' shouldn't break - we treat sleuth as a no-op prefix."""
        from sleuth.repl import parse_line
        assert parse_line("sleuth ask hello") == ["ask", "hello"]

    def test_unbalanced_quote_raises_value_error(self):
        from sleuth.repl import parse_line, ParseError
        with pytest.raises(ParseError):
            parse_line('ask "unclosed')


class TestIsMeta:
    @pytest.mark.parametrize("cmd", ["exit", "quit", "q", "help", "?", "clear", "cls"])
    def test_meta_commands(self, cmd):
        from sleuth.repl import is_meta
        assert is_meta([cmd]) is True

    def test_non_meta(self):
        from sleuth.repl import is_meta
        assert is_meta(["ask", "hi"]) is False
        assert is_meta(["jobs", "list"]) is False
        assert is_meta([]) is False


class TestCompleter:
    """The completer offers known commands and subcommands."""

    def test_top_level_completions_include_known(self):
        from sleuth.repl import top_level_words
        words = top_level_words()
        for expected in ("ask", "models", "jobs", "drive", "history", "show", "setup", "init", "ping", "help", "exit"):
            assert expected in words

    def test_jobs_subcommands(self):
        from sleuth.repl import subcommand_words
        jobs = subcommand_words("jobs")
        for expected in ("new", "list", "show", "edit", "rm", "run", "schedule", "unschedule", "crontab"):
            assert expected in jobs

    def test_unknown_subcommand_returns_empty(self):
        from sleuth.repl import subcommand_words
        assert subcommand_words("nonexistent") == []
