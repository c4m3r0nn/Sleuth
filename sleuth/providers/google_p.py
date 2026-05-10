"""Google Gemini provider via the new google-genai SDK with google_search grounding.

Docs: https://ai.google.dev/gemini-api/docs/google-search
"""

from __future__ import annotations

from typing import Any, Optional

from sleuth.config import get_settings
from sleuth.providers.base import Provider, ResearchResult, Citation


class GoogleProvider(Provider):
    name = "google"

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.google_api_key:
            raise RuntimeError(
                "GOOGLE_API_KEY is not set. Add it to .env or the environment."
            )
        from google import genai

        self._genai = genai
        self._client = genai.Client(api_key=settings.google_api_key)

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
        from google.genai import types

        tools = []
        if web_search:
            tools.append(types.Tool(google_search=types.GoogleSearch()))

        config_kwargs: dict[str, Any] = {}
        if tools:
            config_kwargs["tools"] = tools
        if system:
            config_kwargs["system_instruction"] = system
        if temperature is not None:
            config_kwargs["temperature"] = temperature
        if max_tokens:
            config_kwargs["max_output_tokens"] = max_tokens

        config = types.GenerateContentConfig(**config_kwargs)

        response = self._client.models.generate_content(
            model=model,
            contents=prompt,
            config=config,
        )

        text = getattr(response, "text", "") or ""
        citations: list[Citation] = []
        search_calls = 0
        seen_urls: set[str] = set()

        for cand in getattr(response, "candidates", None) or []:
            grounding = getattr(cand, "grounding_metadata", None)
            if not grounding:
                continue
            queries = getattr(grounding, "web_search_queries", None) or []
            search_calls += len(queries)
            chunks = getattr(grounding, "grounding_chunks", None) or []
            for chunk in chunks:
                web = getattr(chunk, "web", None)
                if not web:
                    continue
                url = getattr(web, "uri", None)
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    citations.append(
                        Citation(url=url, title=getattr(web, "title", None))
                    )

        usage = getattr(response, "usage_metadata", None)
        tokens_in = getattr(usage, "prompt_token_count", 0) or 0
        tokens_out = getattr(usage, "candidates_token_count", 0) or 0

        return ResearchResult(
            provider=self.name,
            model=model,
            text=text,
            citations=citations,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            search_calls=search_calls,
        )
