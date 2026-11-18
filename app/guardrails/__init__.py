"""Input-safety checks used by the geological question-answering path."""

from app.guardrails.injection import detect_prompt_injection

__all__ = ["detect_prompt_injection"]
