"""System prompt, post-processing, and entry point for AI rewrites."""

from __future__ import annotations

from rewrite.config import load_config
from rewrite.providers import ollama
from rewrite.providers.base import BaseProvider
from rewrite.providers.gemini import GeminiProvider
from rewrite.providers.ollama import OllamaProvider

SYSTEM_PROMPT = """\
You are a precise text editor. Your only job is to correct the provided text.

Rules:
- Fix grammar, spelling, punctuation, and capitalization errors
- Detect the language automatically and correct in the same language
- Preserve the original tone, style, vocabulary level, and intent exactly
- Preserve all line breaks and paragraph structure
- Never translate: keep words from other languages exactly as written \
(e.g. an English "Yes" in French text stays "Yes")
- Keep slang, colloquialisms and informal contractions (e.g. "y'a", \
"foufou", "se capter"); only fix their spelling
- Do not add, remove, or rephrase content beyond what is necessary for correctness
- Do not add explanations, comments, quotation marks, or formatting wrappers
- Return ONLY the corrected text, nothing else
- If the text is already correct, return it unchanged
- If the input is a single word, correct its spelling or return it unchanged"""

PROVIDER_LABELS = {"gemini": "Gemini", "ollama": "Ollama"}


def get_provider(config: dict | None = None) -> BaseProvider:
    """Create the provider selected in config (Gemini or local Ollama)."""
    if config is None:
        config = load_config()

    provider = config.get("provider", "gemini")
    if provider == "ollama":
        return OllamaProvider(
            model=config.get("ollama_model", ""),
            url=config.get("ollama_url", ollama.DEFAULT_URL),
        )
    if provider != "gemini":
        raise ValueError(f"Unknown provider {provider!r}. Check Settings.")

    api_key = config.get("gemini_api_key", "")
    if not api_key:
        raise ValueError(
            "Gemini API key not configured. Please set it in Settings."
        )
    return GeminiProvider(
        api_key=api_key,
        model=config.get("gemini_model", "gemini-2.5-flash"),
    )


def clean_response(text: str) -> str:
    """Strip AI artifacts from the response -- quotes, markdown code blocks, etc."""
    text = text.strip()

    # Remove markdown code blocks
    if text.startswith("```") and text.endswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1])

    # Remove surrounding straight quotes
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ('"', "'"):
        text = text[1:-1]

    # Remove surrounding curly quotes
    if text.startswith("\u201c") and text.endswith("\u201d"):
        text = text[1:-1]

    return text.strip()


def rewrite_text(text: str, provider: BaseProvider) -> str:
    """Send text to the provider, return corrected text."""
    result = provider.rewrite(text, system_prompt=SYSTEM_PROMPT)
    return clean_response(result)


