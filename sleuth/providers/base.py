"""The Provider interface and shared result shapes."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Citation:
    url: str
    title: Optional[str] = None
    snippet: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {"url": self.url, "title": self.title, "snippet": self.snippet}


@dataclass
class ResearchResult:
    provider: str
    model: str
    text: str
    citations: list[Citation] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    search_calls: int = 0
    raw: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "text": self.text,
            "citations": [c.to_dict() for c in self.citations],
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "search_calls": self.search_calls,
        }


class Provider(ABC):
    """One implementation per LLM vendor."""

    name: str = ""

    @abstractmethod
    def run(
        self,
        prompt: str,
        *,
        model: str,
        system: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: Optional[float] = None,
        web_search: bool = True,
        max_search_calls: int = 5,
        extra: Optional[dict[str, Any]] = None,
    ) -> ResearchResult:
        """Run a single research turn and return the structured result."""
        raise NotImplementedError
