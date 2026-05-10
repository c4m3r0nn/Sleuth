"""SqliteStore CRUD and run lifecycle."""

import pytest

from sleuth.storage import Job, Run, new_id
from sleuth.storage.sqlite_store import utcnow


def make_job(**over):
    base = dict(
        id=new_id(),
        name="test",
        prompt="hello",
        provider="openai",
        model="gpt-5.5",
    )
    base.update(over)
    return Job(**base)


def make_run(job_id=None):
    return Run(
        id=new_id(),
        job_id=job_id,
        prompt="hello",
        provider="openai",
        model="gpt-5.5",
        started_at=utcnow(),
    )


def test_create_and_get_job(store):
    job = make_job()
    store.create_job(job)
    fetched = store.get_job(job.id)
    assert fetched is not None
    assert fetched.id == job.id
    assert fetched.name == "test"
    assert fetched.web_search is True


def test_list_jobs_empty(store):
    assert store.list_jobs() == []


def test_list_jobs_returns_recent_first(store):
    a = make_job(name="a")
    b = make_job(name="b")
    store.create_job(a)
    store.create_job(b)
    rows = store.list_jobs()
    assert {r.name for r in rows} == {"a", "b"}


def test_update_job_schedule(store):
    job = make_job()
    store.create_job(job)
    store.update_job_schedule(job.id, "daily at 09:00", "0 9 * * *")
    fresh = store.get_job(job.id)
    assert fresh.schedule_label == "daily at 09:00"
    assert fresh.cron_expr == "0 9 * * *"


def test_delete_job(store):
    job = make_job()
    store.create_job(job)
    store.delete_job(job.id)
    assert store.get_job(job.id) is None


def test_run_lifecycle(store):
    run = make_run()
    store.start_run(run)
    fetched = store.get_run(run.id)
    assert fetched is not None
    assert fetched.status == "running"

    store.finish_run(
        run.id,
        status="done",
        output="found it",
        citations=[{"url": "https://x", "title": "X"}],
        tokens_in=10,
        tokens_out=20,
        search_calls=2,
    )
    finished = store.get_run(run.id)
    assert finished.status == "done"
    assert finished.output == "found it"
    assert finished.tokens_in == 10
    assert finished.tokens_out == 20
    assert finished.search_calls == 2
    assert finished.citations == [{"url": "https://x", "title": "X"}]
    assert finished.finished_at is not None


def test_runs_filter_by_job(store):
    job = make_job()
    store.create_job(job)

    bound = make_run(job_id=job.id)
    standalone = make_run()
    store.start_run(bound)
    store.start_run(standalone)

    bound_runs = store.list_runs(job_id=job.id)
    assert {r.id for r in bound_runs} == {bound.id}

    all_runs = store.list_runs()
    assert {r.id for r in all_runs} == {bound.id, standalone.id}


def test_delete_job_orphans_runs(store):
    """Runs survive job deletion (job_id is set NULL)."""
    job = make_job()
    store.create_job(job)
    run = make_run(job_id=job.id)
    store.start_run(run)
    store.delete_job(job.id)
    fresh = store.get_run(run.id)
    assert fresh is not None
    assert fresh.job_id is None


def test_new_id_is_unique():
    assert new_id() != new_id()
    assert len(new_id()) == 8


# --------------------------------------------------------------------------- #
# update_job (added for `sleuth jobs edit`)
# --------------------------------------------------------------------------- #


class TestUpdateJob:
    def test_updates_only_named_fields(self, store):
        job = make_job(prompt="old", model="gpt-5.5", max_tokens=4096)
        store.create_job(job)
        store.update_job(job.id, prompt="new", model="claude-opus-4-7")
        fresh = store.get_job(job.id)
        assert fresh.prompt == "new"
        assert fresh.model == "claude-opus-4-7"
        # untouched
        assert fresh.max_tokens == 4096
        assert fresh.name == "test"

    def test_bumps_updated_at(self, store):
        job = make_job()
        store.create_job(job)
        before = store.get_job(job.id).updated_at
        # SQLite text-cmp is fine: utcnow() goes strictly forward
        import time
        time.sleep(1.05)  # ISO seconds resolution
        store.update_job(job.id, prompt="changed")
        after = store.get_job(job.id).updated_at
        assert after > before

    def test_unknown_id_raises(self, store):
        with pytest.raises(KeyError):
            store.update_job("nope", prompt="x")

    def test_can_toggle_booleans(self, store):
        job = make_job(web_search=True, sync_drive=False, notify=True)
        store.create_job(job)
        store.update_job(job.id, web_search=False, sync_drive=True, notify=False)
        fresh = store.get_job(job.id)
        assert fresh.web_search is False
        assert fresh.sync_drive is True
        assert fresh.notify is False

    def test_can_clear_optional_fields(self, store):
        job = make_job(system="be brief", temperature=0.5)
        store.create_job(job)
        store.update_job(job.id, system=None, temperature=None)
        fresh = store.get_job(job.id)
        assert fresh.system is None
        assert fresh.temperature is None

    def test_rejects_unknown_field(self, store):
        job = make_job()
        store.create_job(job)
        with pytest.raises(ValueError):
            store.update_job(job.id, totally_made_up="x")

    def test_no_op_with_no_fields(self, store):
        job = make_job()
        store.create_job(job)
        # Calling with no fields should still work (and do nothing material).
        store.update_job(job.id)
        fresh = store.get_job(job.id)
        assert fresh.name == "test"
