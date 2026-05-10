"""OpenAI provider via the Responses API with the built-in web_search tool.

Docs: https://developers.openai.com/api/docs/guides/tools-web-search
"""

from __future__ import annotations

from typing import Any, Optional

from sleuth.config import get_settings
from sleuth.providers.base import Provider, ResearchResult, Citation


class OpenAIProvider(Provider):
    name = "openai"

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.openai_api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Add it to .env or the environment."
            )
        # Lazy import so the package can boot without the SDK installed.
        from openai import OpenAI

        self._client = OpenAI(api_key=settings.openai_api_key)

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
        kwargs: dict[str, Any] = {
            "model": model,
            "input": prompt,
        }
        if system:
            kwargs["instructions"] = system
        if max_tokens:
            kwargs["max_output_tokens"] = max_tokens
        if temperature is not None:
            kwargs["temperature"] = temperature

        tools: list[dict[str, Any]] = []
        if web_search:
            tools.append({"type": "web_search"})
        if tools:
            kwargs["tools"] = tools
            # Ask for the full list of consulted sources (not just cited ones).
            kwargs["include"] = ["web_search_call.action.sources"]

        if extra:
            kwargs.update(extra)

        response = self._client.responses.create(**kwargs)

        text = getattr(response, "output_text", "") or ""
        citations: list[Citation] = []
        search_calls = 0

        # Walk the structured output for annotations and tool calls.
        seen_urls: set[str] = set()
        for item in getattr(response, "output", []) or []:
            item_type = getattr(item, "type", None)
            if item_type == "web_search_call":
                search_calls += 1
                action = getattr(item, "action", None)
                sources = getattr(action, "sources", None) if action else None
                for src in sources or []:
                    url = getattr(src, "url", None)
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        citations.append(
                            Citation(url=url, title=getattr(src, "title", None))
                        )
            elif item_type == "message":
                for content in getattr(item, "content", []) or []:
                    for ann in getattr(content, "annotations", []) or []:
                        if getattr(ann, "type", None) == "url_citation":
                            url = getattr(ann, "url", None)
                            if url and url not in seen_urls:
                                seen_urls.add(url)
                                citations.append(
                                    Citation(
                                        url=url,
                                        title=getattr(ann, "title", None),
                                    )
                                )

        usage = getattr(response, "usage", None)
        tokens_in = getattr(usage, "input_tokens", 0) or 0
        tokens_out = getattr(usage, "output_tokens", 0) or 0

        return ResearchResult(
            provider=self.name,
            model=model,
            text=text,
            citations=citations,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            search_calls=search_calls,
        )
