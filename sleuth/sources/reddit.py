"""Reddit fetching + formatting for research runs.

Pre-fetches posts/comments matching a spec, then renders them as a markdown
context block that gets prepended to the LLM prompt. Pure read-only access
via app-only OAuth (client_id + client_secret); no user account required.

Public surface:

  - RedditSearchSpec       : everything the user can configure
  - RedditFetchError       : raised on auth / network / config trouble
  - is_configured()        : True if env has the credentials
  - get_client()           : returns a praw.Reddit (lazy-imports praw)
  - fetch(spec)            : -> RedditDigest
  - format_for_llm(digest) : -> markdown string
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from sleuth.config import get_settings


logger = logging.getLogger(__name__)


# What the user can dial. Kept as plain enums-as-tuples so the CLI/walkthrough
# can use them directly as choice lists.

VALID_SORTS_SEARCH = ("relevance", "top", "new", "hot", "comments")
VALID_SORTS_BROWSE = ("hot", "new", "top", "rising")
VALID_TIME_FILTERS = ("hour", "day", "week", "month", "year", "all")
VALID_COMMENT_STRATEGIES = ("none", "top_score", "top_replies", "all")

# Reddit enforces "<platform>:<app-id>:<version> (by /u/<username>)".
# We don't know the user's reddit handle so we leave that suffix off; the
# wizard nudges users to override this with their own handle. The platform/
# app-id portion still identifies sleuth, which is the policy's main intent.
DEFAULT_USER_AGENT = "sleuth:research:0.1 (personal research tool)"


class RedditFetchError(RuntimeError):
    """Raised when fetching from Reddit fails or isn't configured."""


@dataclass
class RedditSearchSpec:
    """Everything the user can configure for a Reddit pre-fetch.

    subreddits: list of subreddit names without the 'r/' prefix. Empty list
                falls back to r/all (only valid with a query).
    query:      search query. None = browse listing of the subreddits.
    sort:       'relevance' | 'top' | 'new' | 'hot' | 'comments' (search) or
                'hot' | 'new' | 'top' | 'rising' (browse).
    time_filter:'hour'|'day'|'week'|'month'|'year'|'all' — only honoured by
                'top' and search-with-'relevance'.
    top_posts:  cap on posts returned.
    comment_strategy:
                'none'       - skip comments entirely.
                'top_score'  - top N by score across the thread.
                'top_replies'- top N by total descendant count (most discussion).
                'all'        - first N comments in natural order.
    max_comments: cap on comments included per post.
    max_comment_depth: drop comments deeper than this (0 = top-level only).
    truncate_post_chars / truncate_comment_chars: bound the bytes we send to
                the LLM so a single long selftext doesn't blow the context.
    """

    subreddits: list[str] = field(default_factory=list)
    query: Optional[str] = None
    sort: str = "relevance"
    time_filter: str = "week"
    top_posts: int = 10
    comment_strategy: str = "none"
    max_comments: int = 20
    max_comment_depth: int = 3
    truncate_post_chars: int = 2000
    truncate_comment_chars: int = 600

    def validate(self) -> None:
        if self.top_posts < 1:
            raise ValueError("top_posts must be >= 1")
        if self.max_comments < 0:
            raise ValueError("max_comments must be >= 0")
        if self.max_comment_depth < 0:
            raise ValueError("max_comment_depth must be >= 0")
        if self.comment_strategy not in VALID_COMMENT_STRATEGIES:
            raise ValueError(
                f"comment_strategy must be one of {VALID_COMMENT_STRATEGIES}"
            )
        if self.time_filter not in VALID_TIME_FILTERS:
            raise ValueError(f"time_filter must be one of {VALID_TIME_FILTERS}")
        if self.query:
            if self.sort not in VALID_SORTS_SEARCH:
                raise ValueError(
                    f"sort must be one of {VALID_SORTS_SEARCH} when query is set"
                )
        else:
            if not self.subreddits:
                raise ValueError(
                    "need at least one subreddit when no query is given"
                )
            if self.sort not in VALID_SORTS_BROWSE:
                raise ValueError(
                    f"sort must be one of {VALID_SORTS_BROWSE} when only browsing"
                )

    @property
    def subreddit_selector(self) -> str:
        """The string PRAW wants for `reddit.subreddit(...)`."""
        if not self.subreddits:
            return "all"
        return "+".join(_strip_r_prefix(s) for s in self.subreddits if s.strip())


@dataclass
class RedditComment:
    author: str
    score: int
    body: str
    depth: int
    descendant_count: int
    permalink: str


@dataclass
class RedditPost:
    subreddit: str
    title: str
    author: str
    score: int
    num_comments: int
    url: str
    permalink: str
    selftext: str
    created_utc: float
    comments: list[RedditComment] = field(default_factory=list)


@dataclass
class RedditDigest:
    spec: RedditSearchSpec
    posts: list[RedditPost]
    available_posts: Optional[int] = None  # None = unknown (search doesn't tell us)

    def is_empty(self) -> bool:
        return not self.posts


# --------------------------------------------------------------------------- #
# auth + client
# --------------------------------------------------------------------------- #


def is_configured() -> bool:
    s = get_settings()
    return bool(s.reddit_client_id and s.reddit_client_secret)


def get_client():
    """Return a praw.Reddit set up for app-only (read-only) OAuth.

    Lazy-imports praw so importing this module doesn't require the dep at
    every entry point.
    """
    s = get_settings()
    if not (s.reddit_client_id and s.reddit_client_secret):
        raise RedditFetchError(
            "Reddit not configured. Set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET "
            "in .env (see `sleuth setup`)."
        )
    try:
        import praw
    except ImportError as e:
        raise RedditFetchError(
            "praw not installed. Run: pip install -e . (it's in pyproject)."
        ) from e

    user_agent = s.reddit_user_agent or DEFAULT_USER_AGENT
    reddit = praw.Reddit(
        client_id=s.reddit_client_id,
        client_secret=s.reddit_client_secret,
        user_agent=user_agent,
    )
    # Force read-only — we never act as a user; this also lets a 'web' app
    # type work without redirect_uri shenanigans.
    reddit.read_only = True
    return reddit


# --------------------------------------------------------------------------- #
# fetch
# --------------------------------------------------------------------------- #


def fetch(spec: RedditSearchSpec, *, client: Any = None) -> RedditDigest:
    """Pull posts (and optionally comments) per spec. Returns a RedditDigest.

    `client` is for tests — pass a fake reddit object to bypass praw.
    """
    spec.validate()
    reddit = client if client is not None else get_client()

    try:
        subreddit = reddit.subreddit(spec.subreddit_selector)
        listing = _resolve_listing(subreddit, spec)
        posts_raw = list(listing)
    except RedditFetchError:
        raise
    except Exception as e:  # noqa: BLE001 — praw raises a zoo of types
        raise RedditFetchError(f"Reddit fetch failed: {type(e).__name__}: {e}") from e

    posts: list[RedditPost] = []
    for submission in posts_raw[: spec.top_posts]:
        comments = _collect_comments(submission, spec)
        posts.append(
            RedditPost(
                subreddit=str(getattr(submission, "subreddit", "") or ""),
                title=_str(getattr(submission, "title", "")),
                author=_author_name(getattr(submission, "author", None)),
                score=int(getattr(submission, "score", 0) or 0),
                num_comments=int(getattr(submission, "num_comments", 0) or 0),
                url=_str(getattr(submission, "url", "")),
                permalink=_permalink(submission),
                selftext=_truncate(
                    _str(getattr(submission, "selftext", "")),
                    spec.truncate_post_chars,
                ),
                created_utc=float(getattr(submission, "created_utc", 0) or 0),
                comments=comments,
            )
        )

    return RedditDigest(spec=spec, posts=posts)


def _resolve_listing(subreddit, spec: RedditSearchSpec) -> Iterable:
    """Pick the right PRAW call for the spec's sort / query combo."""
    limit = spec.top_posts
    if spec.query:
        return subreddit.search(
            spec.query,
            sort=spec.sort,
            time_filter=spec.time_filter,
            limit=limit,
        )
    if spec.sort == "top":
        return subreddit.top(time_filter=spec.time_filter, limit=limit)
    if spec.sort == "new":
        return subreddit.new(limit=limit)
    if spec.sort == "rising":
        return subreddit.rising(limit=limit)
    return subreddit.hot(limit=limit)


def _collect_comments(submission, spec: RedditSearchSpec) -> list[RedditComment]:
    if spec.comment_strategy == "none" or spec.max_comments == 0:
        return []
    try:
        submission.comment_sort = "top"
        # Drop "load more" stubs so .list() returns concrete comments only.
        submission.comments.replace_more(limit=0)
        flat = submission.comments.list()
    except Exception as e:  # noqa: BLE001
        logger.warning("comment fetch failed for %s: %s", _permalink(submission), e)
        return []

    eligible: list[tuple[Any, int, int]] = []  # (comment, depth, descendants)
    for c in flat:
        depth = int(getattr(c, "depth", 0) or 0)
        if depth > spec.max_comment_depth:
            continue
        eligible.append((c, depth, _descendant_count(c, spec.max_comment_depth)))

    if spec.comment_strategy == "top_score":
        eligible.sort(key=lambda t: int(getattr(t[0], "score", 0) or 0), reverse=True)
    elif spec.comment_strategy == "top_replies":
        eligible.sort(key=lambda t: t[2], reverse=True)
    # "all" keeps natural order from .list() (which is roughly threaded).

    picked = eligible[: spec.max_comments]
    return [
        RedditComment(
            author=_author_name(getattr(c, "author", None)),
            score=int(getattr(c, "score", 0) or 0),
            body=_truncate(_str(getattr(c, "body", "")), spec.truncate_comment_chars),
            depth=depth,
            descendant_count=desc,
            permalink=_permalink(c),
        )
        for (c, depth, desc) in picked
    ]


def _descendant_count(comment, max_depth: int) -> int:
    """Count direct + nested replies under `comment`, ignoring depth>max_depth."""
    total = 0
    try:
        replies = list(getattr(comment, "replies", []) or [])
    except Exception:  # noqa: BLE001
        return 0
    for r in replies:
        if int(getattr(r, "depth", 0) or 0) > max_depth:
            continue
        total += 1 + _descendant_count(r, max_depth)
    return total


def _author_name(author) -> str:
    if author is None:
        return "[deleted]"
    name = getattr(author, "name", None)
    return name or str(author) or "[deleted]"


def _permalink(thing) -> str:
    p = getattr(thing, "permalink", "") or ""
    if p.startswith("http"):
        return p
    if p:
        return f"https://reddit.com{p}"
    return ""


def _str(v) -> str:
    if v is None:
        return ""
    return str(v)


def _strip_r_prefix(name: str) -> str:
    """'r/python' -> 'python'. Plain 'python' passes through unchanged."""
    s = name.strip()
    if s.lower().startswith("r/"):
        return s[2:].strip()
    return s


def _truncate(text: str, limit: int) -> str:
    if limit <= 0 or len(text) <= limit:
        return text
    return text[:limit].rstrip() + f"… [truncated at {limit} chars]"


# --------------------------------------------------------------------------- #
# format
# --------------------------------------------------------------------------- #


def format_for_llm(digest: RedditDigest) -> str:
    """Render a RedditDigest as a markdown block suitable to prepend to a prompt."""
    spec = digest.spec
    lines: list[str] = []
    lines.append("# Reddit context")
    lines.append("")
    lines.append("> Pre-fetched Reddit posts and comments. Treat these as primary")
    lines.append("> sources alongside any web search you do.")
    lines.append("")

    if spec.query:
        lines.append(f"- **Query:** {spec.query}")
    else:
        lines.append("- **Query:** _(none — browsing)_")
    if spec.subreddits:
        subs = ", ".join(f"r/{_strip_r_prefix(s)}" for s in spec.subreddits)
        lines.append(f"- **Subreddits:** {subs}")
    else:
        lines.append("- **Subreddits:** r/all")
    if spec.sort == "top" or (spec.query and spec.sort in ("relevance", "top")):
        lines.append(f"- **Sort:** {spec.sort} (time filter: {spec.time_filter})")
    else:
        lines.append(f"- **Sort:** {spec.sort}")
    lines.append(f"- **Posts included:** {len(digest.posts)} (cap {spec.top_posts})")
    if spec.comment_strategy == "none":
        lines.append("- **Comments:** none")
    else:
        lines.append(
            f"- **Comments per post:** up to {spec.max_comments} via "
            f"{spec.comment_strategy} (max depth {spec.max_comment_depth})"
        )
    lines.append("")

    if not digest.posts:
        lines.append("_(no posts matched)_")
        lines.append("")
        return "\n".join(lines)

    for i, post in enumerate(digest.posts, 1):
        lines.append("---")
        lines.append("")
        lines.append(f"## Post {i} — r/{post.subreddit}")
        lines.append("")
        lines.append(f"**{post.title}**")
        lines.append("")
        meta = (
            f"u/{post.author} · score {post.score} · "
            f"{post.num_comments} comments · posted {_fmt_ts(post.created_utc)}"
        )
        lines.append(meta)
        lines.append("")
        if post.permalink:
            lines.append(f"Permalink: {post.permalink}")
        if post.url and post.url != post.permalink:
            lines.append(f"Link: {post.url}")
        lines.append("")
        if post.selftext.strip():
            lines.append("### Body")
            lines.append("")
            for ln in post.selftext.splitlines():
                lines.append(f"> {ln}" if ln else ">")
            lines.append("")
        if post.comments:
            lines.append(
                f"### Comments ({len(post.comments)} of {post.num_comments}, "
                f"{spec.comment_strategy})"
            )
            lines.append("")
            for j, c in enumerate(post.comments, 1):
                indent = "  " * min(c.depth, 6)
                head = (
                    f"{indent}{j}. **u/{c.author}** "
                    f"(score {c.score}, depth {c.depth}, replies {c.descendant_count})"
                )
                lines.append(head)
                for ln in c.body.splitlines():
                    lines.append(f"{indent}   {ln}" if ln else f"{indent}   ")
                lines.append("")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _fmt_ts(ts: float) -> str:
    if not ts:
        return "(unknown date)"
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime(
            "%Y-%m-%d %H:%M UTC"
        )
    except Exception:  # noqa: BLE001
        return "(unknown date)"


# --------------------------------------------------------------------------- #
# (de)serialisation for storage on a Job row
# --------------------------------------------------------------------------- #


def spec_to_dict(spec: RedditSearchSpec) -> dict[str, Any]:
    return asdict(spec)


def spec_from_dict(d: dict[str, Any]) -> RedditSearchSpec:
    return RedditSearchSpec(
        subreddits=list(d.get("subreddits") or []),
        query=d.get("query"),
        sort=d.get("sort") or "relevance",
        time_filter=d.get("time_filter") or "week",
        top_posts=int(d.get("top_posts") or 10),
        comment_strategy=d.get("comment_strategy") or "none",
        max_comments=int(d.get("max_comments") or 20),
        max_comment_depth=int(d.get("max_comment_depth") or 3),
        truncate_post_chars=int(d.get("truncate_post_chars") or 2000),
        truncate_comment_chars=int(d.get("truncate_comment_chars") or 600),
    )
