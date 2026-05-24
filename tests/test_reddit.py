"""RedditSearchSpec validation, formatting, and Job round-trip.

No real network: the fetch test uses a FakeReddit double passed via the
`client=` kwarg, and the formatter test runs on a hand-built digest.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

import pytest

from sleuth.sources.reddit import (
    RedditDigest,
    RedditPost,
    RedditSearchSpec,
    fetch,
    format_for_llm,
    spec_from_dict,
    spec_to_dict,
)
from sleuth.storage import Job, get_store, new_id


# --------------------------------------------------------------------------- #
# spec validation
# --------------------------------------------------------------------------- #


def test_browse_without_subreddits_is_invalid():
    spec = RedditSearchSpec(sort="hot")  # no query, no subs -> can't browse
    with pytest.raises(ValueError, match="subreddit"):
        spec.validate()


def test_search_query_accepts_search_sorts():
    spec = RedditSearchSpec(query="rust async", sort="relevance")
    spec.validate()  # should not raise


def test_browse_rejects_search_only_sorts():
    spec = RedditSearchSpec(subreddits=["rust"], sort="relevance")
    with pytest.raises(ValueError, match="browsing"):
        spec.validate()


def test_subreddit_selector_joins_with_plus():
    spec = RedditSearchSpec(subreddits=["python", "r/rust"], query="async")
    assert spec.subreddit_selector == "python+rust"


def test_subreddit_selector_defaults_to_all():
    spec = RedditSearchSpec(query="anything")
    assert spec.subreddit_selector == "all"


def test_comment_strategy_must_be_valid():
    spec = RedditSearchSpec(subreddits=["x"], query="y", comment_strategy="nope")
    with pytest.raises(ValueError, match="comment_strategy"):
        spec.validate()


def test_top_posts_must_be_positive():
    spec = RedditSearchSpec(subreddits=["x"], query="y", top_posts=0)
    with pytest.raises(ValueError, match="top_posts"):
        spec.validate()


# --------------------------------------------------------------------------- #
# spec (de)serialisation
# --------------------------------------------------------------------------- #


def test_spec_round_trip_through_dict():
    spec = RedditSearchSpec(
        subreddits=["python", "rust"],
        query="async performance",
        sort="top",
        time_filter="month",
        top_posts=15,
        comment_strategy="top_replies",
        max_comments=12,
        max_comment_depth=4,
    )
    d = spec_to_dict(spec)
    back = spec_from_dict(d)
    assert back == spec


# --------------------------------------------------------------------------- #
# fetch with a fake PRAW double
# --------------------------------------------------------------------------- #


@dataclass
class FakeAuthor:
    name: str


@dataclass
class FakeComment:
    body: str
    score: int
    depth: int = 0
    author: FakeAuthor | None = None
    permalink: str = "/r/x/comments/abc/_/d"
    replies: list["FakeComment"] = field(default_factory=list)


@dataclass
class FakeSubmissionComments:
    """Mimics a praw CommentForest enough for our fetch path."""
    _flat: list[FakeComment]

    def replace_more(self, limit=0):
        pass

    def list(self):
        return list(self._flat)


@dataclass
class FakeSubmission:
    title: str
    selftext: str
    score: int
    num_comments: int
    url: str
    permalink: str
    created_utc: float
    subreddit: str
    author: FakeAuthor
    comment_sort: str = "top"
    _comments: list[FakeComment] = field(default_factory=list)

    @property
    def comments(self):
        return FakeSubmissionComments(self._comments)


class FakeSubreddit:
    def __init__(self, posts: list[FakeSubmission]):
        self._posts = posts

    def search(self, query, sort="relevance", time_filter="week", limit=10):
        return iter(self._posts[:limit])

    def hot(self, limit=10):
        return iter(self._posts[:limit])

    def top(self, time_filter="week", limit=10):
        return iter(self._posts[:limit])

    def new(self, limit=10):
        return iter(self._posts[:limit])

    def rising(self, limit=10):
        return iter(self._posts[:limit])


class FakeReddit:
    def __init__(self, posts):
        self._posts = posts
        self.read_only = False

    def subreddit(self, name):
        return FakeSubreddit(self._posts)


def _make_fake_posts() -> list[FakeSubmission]:
    c1 = FakeComment(body="great point", score=42, depth=0, author=FakeAuthor("alice"))
    c2 = FakeComment(
        body="huh wait", score=5, depth=1, author=FakeAuthor("bob"),
        replies=[FakeComment(body="ok", score=2, depth=2, author=FakeAuthor("carol"))],
    )
    c1.replies = [c2]
    return [
        FakeSubmission(
            title="GPT-5.5 results",
            selftext="long body " * 5,
            score=1234,
            num_comments=567,
            url="https://example.com/abc",
            permalink="/r/test/comments/abc/_",
            created_utc=1700000000.0,
            subreddit="test",
            author=FakeAuthor("op"),
            _comments=[c1, c2],  # flat .list() returns these in order
        ),
        FakeSubmission(
            title="Second post",
            selftext="",
            score=10,
            num_comments=0,
            url="https://example.com/def",
            permalink="/r/test/comments/def/_",
            created_utc=1700000100.0,
            subreddit="test",
            author=FakeAuthor("op2"),
        ),
    ]


def test_fetch_returns_posts_and_selected_comments():
    spec = RedditSearchSpec(
        subreddits=["test"],
        query="anything",
        sort="relevance",
        top_posts=10,
        comment_strategy="top_score",
        max_comments=10,
        max_comment_depth=3,
    )
    fake = FakeReddit(_make_fake_posts())
    digest = fetch(spec, client=fake)
    assert len(digest.posts) == 2
    first = digest.posts[0]
    assert first.title == "GPT-5.5 results"
    assert first.score == 1234
    # top_score should rank alice's 42 above bob's 5.
    assert first.comments[0].author == "alice"
    assert first.comments[0].score == 42


def test_fetch_skips_comments_when_strategy_none():
    spec = RedditSearchSpec(
        subreddits=["test"], query="x", sort="relevance",
        top_posts=10, comment_strategy="none",
    )
    fake = FakeReddit(_make_fake_posts())
    digest = fetch(spec, client=fake)
    assert all(not p.comments for p in digest.posts)


def test_fetch_top_replies_prefers_threaded_comments():
    """alice has the deepest sub-thread, so top_replies should rank her first."""
    spec = RedditSearchSpec(
        subreddits=["test"], query="x", sort="relevance",
        top_posts=1, comment_strategy="top_replies",
        max_comments=2, max_comment_depth=3,
    )
    fake = FakeReddit(_make_fake_posts())
    digest = fetch(spec, client=fake)
    first_post = digest.posts[0]
    assert first_post.comments[0].author == "alice"


def test_fetch_respects_max_comment_depth():
    spec = RedditSearchSpec(
        subreddits=["test"], query="x", sort="relevance",
        top_posts=1, comment_strategy="all",
        max_comments=10, max_comment_depth=0,  # top-level only
    )
    fake = FakeReddit(_make_fake_posts())
    digest = fetch(spec, client=fake)
    depths = [c.depth for c in digest.posts[0].comments]
    assert depths == [0]


# --------------------------------------------------------------------------- #
# format_for_llm
# --------------------------------------------------------------------------- #


def test_format_for_llm_header_includes_meta():
    spec = RedditSearchSpec(
        subreddits=["python", "rust"], query="async",
        sort="top", time_filter="month", top_posts=5, comment_strategy="top_score",
    )
    digest = RedditDigest(spec=spec, posts=[])
    out = format_for_llm(digest)
    assert "# Reddit context" in out
    assert "r/python" in out and "r/rust" in out
    assert "top" in out and "month" in out
    assert "_(no posts matched)_" in out


def test_format_for_llm_renders_posts_and_comments():
    posts = [
        RedditPost(
            subreddit="test", title="title", author="alice", score=10,
            num_comments=2, url="https://reddit.com/x", permalink="https://reddit.com/x",
            selftext="hello body", created_utc=1700000000.0,
        ),
    ]
    posts[0].comments  # default factory -> empty
    spec = RedditSearchSpec(subreddits=["test"], query="x", sort="relevance")
    digest = RedditDigest(spec=spec, posts=posts)
    out = format_for_llm(digest)
    assert "## Post 1 — r/test" in out
    assert "**title**" in out
    assert "u/alice" in out
    assert "hello body" in out


# --------------------------------------------------------------------------- #
# job round-trip with reddit settings
# --------------------------------------------------------------------------- #


def test_job_round_trip_with_reddit_settings(store):
    spec = RedditSearchSpec(
        subreddits=["python"], query="asyncio bug",
        sort="top", time_filter="week", top_posts=8,
        comment_strategy="top_score", max_comments=15,
    )
    spec.validate()
    job = Job(
        id=new_id(),
        name="reddit-job",
        prompt="what's hot in python this week?",
        provider="openai",
        model="gpt-5.5",
        reddit_enabled=True,
        reddit_spec=spec_to_dict(spec),
    )
    store.create_job(job)
    fresh = store.get_job(job.id)
    assert fresh is not None
    assert fresh.reddit_enabled is True
    assert fresh.reddit_spec is not None
    back = spec_from_dict(fresh.reddit_spec)
    assert back == spec


def test_build_ask_argv_emits_reddit_flags():
    from sleuth.walkthrough import build_ask_argv
    out = build_ask_argv(
        "hello",
        reddit={
            "enabled": True,
            "subreddits": ["python", "rust"],
            "query": "asyncio",
            "sort": "top",
            "time_filter": "week",
            "top_posts": 8,
            "comment_strategy": "top_score",
            "max_comments": 15,
            "max_depth": 2,
        },
    )
    assert "--reddit" in out
    assert "--reddit-sub" in out
    sub_arg = out[out.index("--reddit-sub") + 1]
    assert sub_arg == "python,rust"
    assert out[out.index("--reddit-sort") + 1] == "top"
    assert out[out.index("--reddit-top") + 1] == "8"
    assert out[out.index("--reddit-comments") + 1] == "top_score"


def test_build_ask_argv_omits_reddit_when_disabled():
    from sleuth.walkthrough import build_ask_argv
    out = build_ask_argv("hello", reddit={"enabled": False})
    assert "--reddit" not in out


def test_build_jobs_edit_argv_no_reddit_when_disabled():
    from sleuth.walkthrough import build_jobs_edit_argv
    out = build_jobs_edit_argv("abc123", reddit={"enabled": False})
    assert "--no-reddit" in out
    assert "--reddit-sub" not in out


def test_update_job_can_clear_reddit(store):
    spec = RedditSearchSpec(subreddits=["x"], query="y", sort="relevance")
    job = Job(
        id=new_id(), name="n", prompt="p", provider="openai", model="gpt-5.5",
        reddit_enabled=True, reddit_spec=spec_to_dict(spec),
    )
    store.create_job(job)
    store.update_job(job.id, reddit_enabled=False, reddit_spec=None)
    fresh = store.get_job(job.id)
    assert fresh.reddit_enabled is False
    assert fresh.reddit_spec is None
