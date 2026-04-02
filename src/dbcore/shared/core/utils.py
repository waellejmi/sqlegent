"""Utility functions for dbcore."""

from __future__ import annotations


def fuzzy_match(pattern: str, text: str) -> tuple[bool, list[int]]:
    if not pattern:
        return True, []

    pattern = pattern.lower()
    text_lower = text.lower()

    pattern_idx = 0
    indices = []

    for i, char in enumerate(text_lower):
        if pattern_idx < len(pattern) and char == pattern[pattern_idx]:
            indices.append(i)
            pattern_idx += 1

    return pattern_idx == len(pattern), indices


def highlight_matches(text: str, indices: list[int], style: str = "bold yellow") -> str:
    if not indices:
        return text

    result = []
    idx_set = set(indices)

    for i, char in enumerate(text):
        if i in idx_set:
            result.append(f"[{style}]{char}[/]")
        else:
            result.append(char)

    return "".join(result)


def format_duration_ms(ms: float, *, always_seconds: bool = False) -> str:
    if always_seconds:
        return f"{ms / 1000:.2f}s"
    if ms >= 1000:
        return f"{ms / 1000:.2f}s"
    if ms >= 1:
        return f"{ms:.0f}ms"
    return f"{ms:.2f}ms"
