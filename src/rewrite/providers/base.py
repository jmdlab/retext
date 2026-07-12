"""Abstract base class for AI providers."""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseProvider(ABC):
    """Base interface that all AI rewrite providers must implement."""

    @abstractmethod
    def rewrite(self, text: str, system_prompt: str = "") -> str:
        """Send text to the AI model for correction.

        Args:
            text: The user text to correct.
            system_prompt: Optional system-level instruction for the model.

        Returns:
            The corrected text.
        """
        ...
