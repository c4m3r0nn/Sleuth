"""The walkthrough text prompt shows a '>' on its own line and styles input."""

import pytest


class TestPromptLabel:
    def test_label_contains_question_and_chevron(self):
        from sleuth.walkthrough import _walkthrough_prompt_label
        ft = _walkthrough_prompt_label("what should sleuth dig up?")
        # FormattedText is a list of (style_class, text) tuples — flatten.
        text = "".join(chunk[1] for chunk in ft)
        assert "what should sleuth dig up?" in text
        assert ">" in text

    def test_label_has_newline_before_chevron(self):
        """Question and input prompt should be on different lines."""
        from sleuth.walkthrough import _walkthrough_prompt_label
        ft = _walkthrough_prompt_label("hello?")
        text = "".join(chunk[1] for chunk in ft)
        # The chevron appears after a newline so it sits on its own line.
        assert "\n" in text
        before_chevron, _, after_chevron = text.partition(">")
        assert before_chevron.endswith("  ") or before_chevron.rstrip().endswith("\n  ")

    def test_question_and_chevron_have_distinct_styles(self):
        """Two formatted-text segments with different class names."""
        from sleuth.walkthrough import _walkthrough_prompt_label
        ft = _walkthrough_prompt_label("anything")
        classes = {chunk[0] for chunk in ft}
        # Expect at least two distinct style classes (so they render in
        # different colours), e.g. 'class:wkq' for the question and
        # 'class:wkprompt' for the '>' line.
        non_empty = {c for c in classes if c}
        assert len(non_empty) >= 2


class TestPromptStyle:
    def test_style_defines_input_class(self):
        from sleuth.walkthrough import _walkthrough_style
        style = _walkthrough_style()
        # The style dict should style: the question, the chevron, and
        # the user's input (empty-key class). prompt_toolkit stores the
        # rule keys without the 'class:' prefix.
        keys = {rule[0] for rule in style.style_rules}
        assert "wkq" in keys
        assert "wkprompt" in keys
        # Empty key styles the actual typed input.
        assert "" in keys
