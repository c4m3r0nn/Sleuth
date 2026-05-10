"""Anthropic provider via the Messages API with the server-side web_search tool.

Docs: https://platform.claude.com/docs/en/docs/agents-and-tools/tool-use/web-search-tool
"""

from __future__ import annotations

from typing import Any, Optional

from sleuth.config import get_settings
from sleuth.providers.base import Provider, ResearchResult, Citation


# We pick the broadly-supported, simpler tool version. The newer
# web_search_20260209 adds dynamic filtering but requires the code_execution
# tool to also be enabled, which adds complexity & cost.
WEB_SEARCH_TOOL_VERSION = "web_search_20250305"


class AnthropicProvider(Provider):
    name = "anthropic"

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.anthropic_api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Add it to .env or the environment."
            )
        from anthropic import Anthropic

        self._client = Anthropic(api_key=settings.anthropic_api_key)

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
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system
        if temperature is not None:
            kwargs["temperature"] = temperature

        tools: list[dict[str, Any]] = []
        if web_search:
            tools.append(
                {
                    "type": WEB_SEARCH_TOOL_VERSION,
                    "name": "web_search",
                    "max_uses": max_search_calls,
                }
            )
        if tools:
            kwargs["tools"] = tools

        if extra:
            kwargs.update(extra)

        response = self._client.messages.create(**kwargs)

        text_parts: list[str] = []
        citations: list[Citation] = []
        seen_urls: set[str] = set()
        search_calls = 0

        for block in response.content:
            block_type = getattr(block, "type", None)
            if block_type == "text":
                text_parts.append(getattr(block, "text", "") or "")
                for cite in getattr(block, "citations", None) or []:
                    url = getattr(cite, "url", None)
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        citations.append(
                            Citation(
                                url=url,
                                title=getattr(cite, "title", None),
                                snippet=getattr(cite, "cited_text", None),
                            )
                        )
            elif block_type == "server_tool_use":
                if getattr(block, "name", "") == "web_search":
                    search_calls += 1
            elif block_type == "web_search_tool_result":
                # Server returns a content list of web_search_result items.
                for r in getattr(block, "content", None) or []:
                    url = getattr(r, "url", None)
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        citations.append(
                            Citation(url=url, title=getattr(r, "title", None))
                        )

        usage = getattr(response, "usage", None)
        tokens_in = getattr(usage, "input_tokens", 0) or 0
        tokens_out = getattr(usage, "output_tokens", 0) or 0
        # If the SDK exposes server_tool_use counts, prefer them.
        st = getattr(usage, "server_tool_use", None)
        if st is not None:
            search_calls = getattr(st, "web_search_requests", search_calls) or search_calls

        return ResearchResult(
            provider=self.name,
            model=model,
            text="".join(text_parts).strip(),
            citations=citations,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            search_calls=search_calls,
        )
