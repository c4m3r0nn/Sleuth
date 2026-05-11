"""Pure state machines for inline single- and multi-select widgets."""

import pytest


# --------------------------------------------------------------------------- #
# SelectorState (single-select)
# --------------------------------------------------------------------------- #


class TestSelectorState:
    def test_starts_at_default_index(self):
        from sleuth.ui.selector import SelectorState
        s = SelectorState(["a", "b", "c"], initial_index=1)
        assert s.index == 1
        assert s.current() == "b"

    def test_clamps_out_of_range_initial(self):
        from sleuth.ui.selector import SelectorState
        s = SelectorState(["a", "b"], initial_index=99)
        assert s.index == 1
        s2 = SelectorState(["a", "b"], initial_index=-3)
        assert s2.index == 0

    def test_move_down_wraps(self):
        from sleuth.ui.selector import SelectorState
        s = SelectorState(["a", "b", "c"])
        s.move_down(); assert s.current() == "b"
        s.move_down(); assert s.current() == "c"
        s.move_down(); assert s.current() == "a"  # wrap

    def test_move_up_wraps(self):
        from sleuth.ui.selector import SelectorState
        s = SelectorState(["a", "b", "c"])
        s.move_up(); assert s.current() == "c"  # wrap up

    def test_select(self):
        from sleuth.ui.selector import SelectorState
        s = SelectorState(["a", "b"])
        s.move_down()
        s.confirm()
        assert s.chosen == "b"
        assert s.done is True
        assert s.cancelled is False

    def test_cancel(self):
        from sleuth.ui.selector import SelectorState
        s = SelectorState(["a", "b"])
        s.cancel()
        assert s.cancelled is True
        assert s.done is True
        assert s.chosen is None

    def test_empty_options_safe(self):
        from sleuth.ui.selector import SelectorState
        s = SelectorState([])
        assert s.current() is None
        s.move_up()   # no crash
        s.move_down()
        s.confirm()
        assert s.chosen is None


# --------------------------------------------------------------------------- #
# MultiSelectorState
# --------------------------------------------------------------------------- #


class TestMultiSelectorState:
    def test_starts_with_no_selections(self):
        from sleuth.ui.selector import MultiSelectorState
        m = MultiSelectorState(["a", "b", "c"])
        assert m.selected == set()
        assert m.index == 0

    def test_starts_with_defaults(self):
        from sleuth.ui.selector import MultiSelectorState
        m = MultiSelectorState(["a", "b", "c"], default_selected=["b"])
        assert m.selected == {"b"}

    def test_toggle(self):
        from sleuth.ui.selector import MultiSelectorState
        m = MultiSelectorState(["a", "b", "c"])
        m.toggle()  # toggle a
        assert m.selected == {"a"}
        m.toggle()  # untoggle a
        assert m.selected == set()
        m.move_down()
        m.toggle()  # toggle b
        assert m.selected == {"b"}

    def test_continue_row_at_end(self):
        from sleuth.ui.selector import MultiSelectorState
        m = MultiSelectorState(["a", "b"])
        # The continue sentinel sits at the end of the navigable list.
        m.move_down()  # b
        m.move_down()  # continue
        assert m.on_continue() is True

    def test_confirm_on_continue_marks_done(self):
        from sleuth.ui.selector import MultiSelectorState
        m = MultiSelectorState(["a", "b"], default_selected=["a"])
        m.move_down()  # b
        m.move_down()  # continue
        m.confirm()
        assert m.done is True
        assert m.cancelled is False
        assert m.result() == ["a"]

    def test_confirm_on_option_toggles_does_not_finish(self):
        """Enter on an option toggles it; enter on continue commits."""
        from sleuth.ui.selector import MultiSelectorState
        m = MultiSelectorState(["a", "b"])
        m.confirm()  # at index 0 -> toggle a
        assert m.done is False
        assert m.selected == {"a"}

    def test_cancel(self):
        from sleuth.ui.selector import MultiSelectorState
        m = MultiSelectorState(["a", "b"], default_selected=["a"])
        m.cancel()
        assert m.cancelled is True
        assert m.done is True

    def test_result_preserves_input_order(self):
        from sleuth.ui.selector import MultiSelectorState
        m = MultiSelectorState(["alpha", "bravo", "charlie", "delta"])
        # toggle out of order
        m.move_down()  # bravo
        m.toggle()
        m.move_down(); m.move_down()  # delta
        m.toggle()
        m.move_up(); m.move_up(); m.move_up()  # alpha
        m.toggle()
        assert m.result() == ["alpha", "bravo", "delta"]

    def test_navigation_wraps_through_continue(self):
        from sleuth.ui.selector import MultiSelectorState
        m = MultiSelectorState(["a", "b"])
        # index 0 -> up wraps to continue (last row)
        m.move_up()
        assert m.on_continue() is True

    def test_total_rows_includes_continue(self):
        from sleuth.ui.selector import MultiSelectorState
        m = MultiSelectorState(["x", "y", "z"])
        assert m.total_rows == 4  # 3 options + continue
