"""Capture → rewrite → paste → restore — shared by the Windows and macOS apps."""

from __future__ import annotations

import logging
from collections.abc import Callable

from rewrite.clipboard import (
    capture_selection,
    replace_selection,
    restore_clipboard,
    save_clipboard,
)
from rewrite.logbuffer import log_buffer
from rewrite.providers.base import BaseProvider
from rewrite.rewriter import rewrite_text

log = logging.getLogger(__name__)


def run_rewrite(
    get_provider: Callable[[], BaseProvider],
    set_status: Callable[[str], None],
) -> None:
    """Rewrite the current selection in place, reporting progress via *set_status*."""
    log_buffer.append("Hotkey triggered")
    set_status("Capturing…")

    original_clipboard = save_clipboard()
    try:
        text = capture_selection()
        if not text:
            log_buffer.append("No text selected — skipped")
            set_status("Ready")
            return

        preview = text[:60].replace("\n", " ")
        log_buffer.append(f"Captured {len(text)} chars: \"{preview}\"")
        set_status("Rewriting…")
        log_buffer.append("Sending to Gemini…")

        corrected = rewrite_text(text, get_provider())

        if corrected and corrected != text:
            replace_selection(corrected)
            log_buffer.append(
                f"Done — replaced ({len(text)} → {len(corrected)} chars)",
            )
            set_status("Done!")
        else:
            log_buffer.append("No changes needed")
            set_status("Ready")
    except Exception as exc:
        log_buffer.append(f"Error: {exc}")
        set_status("Error")
        log.exception("Pipeline error")
    finally:
        restore_clipboard(original_clipboard)
