"""Pure helpers from workflows.runner."""

from sleuth.providers.base import Citation, ResearchResult
from sleuth.workflows.runner import _slugify, _markdown_for_run


class TestSlugify:
    def test_basic(self):
        assert _slugify("Hello, World!") == "hello-world"

    def test_truncates(self):
        s = _slugify("a" * 100)
        assert len(s) <= 50

    def test_handles_empty(self):
        assert _slugify("   ") == "run"

    def test_strips_path_chars(self):
        s = _slugify("../../etc/passwd")
        assert "/" not in s
        assert ".." not in s


class TestMarkdownForRun:
    def _result(self, **over):
        base = dict(
            provider="openai",
            model="gpt-5.5",
            text="findings here",
            citations=[Citation(url="https://x", title="X site")],
            tokens_in=10,
            tokens_out=20,
            search_calls=1,
        )
        base.update(over)
        return ResearchResult(**base)

    def test_includes_prompt_and_findings(self):
        md = _markdown_for_run(
            prompt="why is the sky blue",
            result=self._result(),
            started_at="2026-05-10T12:00:00",
        )
        assert "why is the sky blue" in md
        assert "findings here" in md
        assert "openai" in md
        assert "gpt-5.5" in md

    def test_renders_sources(self):
        md = _markdown_for_run(
            prompt="x",
            result=self._result(),
            started_at="2026-05-10T12:00:00",
        )
        assert "## Sources" in md
        assert "[X site](https://x)" in md

    def test_no_sources_section_when_empty(self):
        md = _markdown_for_run(
            prompt="x",
            result=self._result(citations=[]),
            started_at="2026-05-10T12:00:00",
        )
        assert "## Sources" not in md

    def test_token_footer(self):
        md = _markdown_for_run(
            prompt="x",
            result=self._result(),
            started_at="2026-05-10T12:00:00",
        )
        assert "10/20" in md
        assert "1" in md
