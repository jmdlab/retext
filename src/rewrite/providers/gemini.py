"""Google Gemini provider — uses API key."""

from __future__ import annotations

from google import genai

from rewrite.providers.base import BaseProvider

REQUEST_TIMEOUT_MS = 30_000


class GeminiProvider(BaseProvider):
    """Gemini provider authenticated with an API key.

    The underlying client is created once and reused across requests so the
    TLS connection survives between rewrites.
    """

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash") -> None:
        self.client = genai.Client(
            api_key=api_key,
            http_options=genai.types.HttpOptions(timeout=REQUEST_TIMEOUT_MS),
        )
        self.model = model

    def rewrite(self, text: str, system_prompt: str = "") -> str:
        config = genai.types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.1,
            thinking_config=self._thinking_config(),
        )
        response = self.client.models.generate_content(
            model=self.model,
            contents=text,
            config=config,
        )
        return response.text or text

    def _thinking_config(self) -> genai.types.ThinkingConfig | None:
        """Disable thinking on flash models — pointless for proofreading.

        Pro models reject a zero thinking budget, so leave them at their
        default there.
        """
        if "flash" in self.model:
            return genai.types.ThinkingConfig(thinking_budget=0)
        return None
