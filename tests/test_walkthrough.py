"""Pure argv builders for the REPL walkthroughs."""

import pytest


class TestBuildAskArgv:
    def test_minimum(self):
        from sleuth.walkthrough import build_ask_argv
        assert build_ask_argv("hello") == ["ask", "hello"]

    def test_quotes_not_added(self):
        """The argv form means we never need quotes - the prompt is one token."""
        from sleuth.walkthrough import build_ask_argv
        out = build_ask_argv("a multi word prompt with spaces")
        assert out == ["ask", "a multi word prompt with spaces"]

    def test_with_model(self):
        from sleuth.walkthrough import build_ask_argv
        out = build_ask_argv("hi", model="claude-opus-4-7")
        assert "--model" in out
        assert "claude-opus-4-7" in out

    def test_provider_and_model(self):
        from sleuth.walkthrough import build_ask_argv
        out = build_ask_argv("hi", model="gpt-5.5", provider="openai")
        assert out.count("--model") == 1
        assert out.count("--provider") == 1

    def test_no_search_flag(self):
        from sleuth.walkthrough import build_ask_argv
        out = build_ask_argv("hi", web_search=False)
        assert "--no-search" in out

    def test_search_default_doesnt_emit_flag(self):
        from sleuth.walkthrough import build_ask_argv
        out = build_ask_argv("hi", web_search=True)
        assert "--no-search" not in out

    def test_drive_and_notify(self):
        from sleuth.walkthrough import build_ask_argv
        out = build_ask_argv("hi", drive=True, notify=True)
        assert "--drive" in out
        assert "--notify" in out

    def test_temp_and_max_tokens(self):
        from sleuth.walkthrough import build_ask_argv
        out = build_ask_argv("hi", temperature=0.7, max_tokens=8000)
        assert "--temp" in out
        assert "0.7" in out
        assert "--max-tokens" in out
        assert "8000" in out

    def test_system(self):
        from sleuth.walkthrough import build_ask_argv
        out = build_ask_argv("hi", system="you are concise")
        i = out.index("--system")
        assert out[i + 1] == "you are concise"


class TestBuildJobsNewArgv:
    def test_minimum(self):
        from sleuth.walkthrough import build_jobs_new_argv
        out = build_jobs_new_argv(
            name="morning", prompt="news", model="gpt-5.5", provider="openai"
        )
        assert out[:2] == ["jobs", "new"]
        for flag, val in [
            ("--name", "morning"),
            ("--prompt", "news"),
            ("--model", "gpt-5.5"),
            ("--provider", "openai"),
        ]:
            assert flag in out
            assert val in out

    def test_no_notify_default_true_so_omitted(self):
        from sleuth.walkthrough import build_jobs_new_argv
        out = build_jobs_new_argv(
            name="x", prompt="y", model="m", provider="openai", notify=True
        )
        # `notify=True` matches the underlying CLI default; we don't need to
        # emit anything for it. (Emitting --notify is also fine; current
        # builder simply omits it to keep argv small.)
        assert "--no-notify" not in out

    def test_no_notify_emits_flag(self):
        from sleuth.walkthrough import build_jobs_new_argv
        out = build_jobs_new_argv(
            name="x", prompt="y", model="m", provider="openai", notify=False
        )
        assert "--no-notify" in out

    def test_drive_flag(self):
        from sleuth.walkthrough import build_jobs_new_argv
        out = build_jobs_new_argv(
            name="x", prompt="y", model="m", provider="openai", sync_drive=True
        )
        assert "--drive" in out


class TestBuildJobsScheduleArgv:
    def test_daily(self):
        from sleuth.walkthrough import build_jobs_schedule_argv
        out = build_jobs_schedule_argv("abc", daily="09:00")
        assert out == ["jobs", "schedule", "abc", "--daily", "09:00"]

    def test_weekly(self):
        from sleuth.walkthrough import build_jobs_schedule_argv
        out = build_jobs_schedule_argv("abc", weekly="mon,wed,fri", at="18:30")
        assert "--weekly" in out
        assert "mon,wed,fri" in out
        assert "--at" in out
        assert "18:30" in out

    def test_hourly(self):
        from sleuth.walkthrough import build_jobs_schedule_argv
        out = build_jobs_schedule_argv("abc", hourly=True)
        assert "--hourly" in out

    def test_every(self):
        from sleuth.walkthrough import build_jobs_schedule_argv
        out = build_jobs_schedule_argv("abc", every="15m")
        assert "--every" in out
        assert "15m" in out

    def test_monthly(self):
        from sleuth.walkthrough import build_jobs_schedule_argv
        out = build_jobs_schedule_argv("abc", monthly=True, day=1, at="06:00")
        assert "--monthly" in out
        assert "--day" in out
        assert "1" in out
        assert "--at" in out

    def test_raw_cron(self):
        from sleuth.walkthrough import build_jobs_schedule_argv
        out = build_jobs_schedule_argv("abc", cron="*/30 9-17 * * 1-5")
        i = out.index("--cron")
        assert out[i + 1] == "*/30 9-17 * * 1-5"


class TestSimpleBuilders:
    def test_show(self):
        from sleuth.walkthrough import build_show_argv
        assert build_show_argv("run-id") == ["show", "run-id"]

    def test_history_default(self):
        from sleuth.walkthrough import build_history_argv
        assert build_history_argv() == ["history"]

    def test_history_with_limit_and_job(self):
        from sleuth.walkthrough import build_history_argv
        out = build_history_argv(limit=5, job_id="abc")
        assert "--limit" in out
        assert "5" in out
        assert "--job" in out
        assert "abc" in out

    def test_jobs_run(self):
        from sleuth.walkthrough import build_jobs_run_argv
        assert build_jobs_run_argv("abc") == ["jobs", "run", "abc"]

    def test_jobs_show(self):
        from sleuth.walkthrough import build_jobs_show_argv
        assert build_jobs_show_argv("abc") == ["jobs", "show", "abc"]

    def test_jobs_rm(self):
        from sleuth.walkthrough import build_jobs_rm_argv
        assert build_jobs_rm_argv("abc") == ["jobs", "rm", "abc"]

    def test_jobs_rm_force(self):
        from sleuth.walkthrough import build_jobs_rm_argv
        out = build_jobs_rm_argv("abc", force=True)
        assert "--force" in out


class TestNeedsWalkthrough:
    """Detect bare command names in the REPL that should trigger a walkthrough."""

    def test_bare_ask(self):
        from sleuth.walkthrough import needs_walkthrough
        assert needs_walkthrough(["ask"]) == "ask"

    def test_ask_with_args_does_not(self):
        from sleuth.walkthrough import needs_walkthrough
        assert needs_walkthrough(["ask", "what's up"]) is None

    def test_bare_jobs_new(self):
        from sleuth.walkthrough import needs_walkthrough
        assert needs_walkthrough(["jobs", "new"]) == "jobs new"

    def test_bare_jobs_schedule_without_id(self):
        """Just `jobs schedule` is ambiguous - we walk the user through it."""
        from sleuth.walkthrough import needs_walkthrough
        assert needs_walkthrough(["jobs", "schedule"]) == "jobs schedule"

    def test_jobs_schedule_with_id_already_no_walk(self):
        """If they pass an id but no schedule flag, that's a CLI error - let typer handle it."""
        from sleuth.walkthrough import needs_walkthrough
        assert needs_walkthrough(["jobs", "schedule", "abc"]) is None

    def test_unknown(self):
        from sleuth.walkthrough import needs_walkthrough
        assert needs_walkthrough(["models"]) is None
        assert needs_walkthrough([]) is None

    def test_bare_jobs_opens_menu(self):
        from sleuth.walkthrough import needs_walkthrough
        # Bare `jobs` should walk - we render a menu of subcommands rather
        # than typer's bare usage error.
        assert needs_walkthrough(["jobs"]) == "jobs menu"

    def test_bare_drive_opens_menu(self):
        from sleuth.walkthrough import needs_walkthrough
        assert needs_walkthrough(["drive"]) == "drive menu"

    def test_bare_jobs_logs_walks(self):
        from sleuth.walkthrough import needs_walkthrough
        assert needs_walkthrough(["jobs", "logs"]) == "jobs logs"

    def test_bare_jobs_check_walks(self):
        from sleuth.walkthrough import needs_walkthrough
        assert needs_walkthrough(["jobs", "check"]) == "jobs check"
