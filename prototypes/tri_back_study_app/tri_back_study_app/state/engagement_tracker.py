"""Engagement metrics for session logging."""

from __future__ import annotations

import statistics
import time
from typing import Any


def word_char_counts(text: str) -> tuple[int, int]:
    words = [w for w in text.split() if w.strip()]
    return len(words), len(text)


def recompute_engagement(
    engagement: dict[str, Any],
    *,
    time_on_task_sec: float,
) -> dict[str, Any]:
    turns = engagement.get("turns") or []
    total_words = sum(int(t.get("user_word_count", 0)) for t in turns)
    total_chars = sum(int(t.get("user_char_count", 0)) for t in turns)
    rtts = [float(t.get("round_trip_ms", 0)) for t in turns if t.get("round_trip_ms") is not None]
    engagement["total_user_words"] = total_words
    engagement["total_user_chars"] = total_chars
    engagement["mean_round_trip_ms"] = statistics.mean(rtts) if rtts else 0.0
    engagement["median_round_trip_ms"] = statistics.median(rtts) if rtts else 0.0
    engagement["session_duration_sec"] = time_on_task_sec
    return engagement


def feedback_tallies(messages: list[dict[str, Any]]) -> tuple[int, int]:
    up = down = 0
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        fb = msg.get("feedback") or {}
        rating = fb.get("rating")
        if rating == "up":
            up += 1
        elif rating == "down":
            down += 1
    return up, down


class EngagementTracker:
    def __init__(self, idle_timeout_sec: float = 60.0) -> None:
        self.idle_timeout_sec = idle_timeout_sec
        self._last_active = time.monotonic()
        self._active_accum = 0.0
        self._composer_started: float | None = None
        self._idle_before_turn = 0.0

    def mark_active(self) -> None:
        now = time.monotonic()
        gap = now - self._last_active
        if gap <= self.idle_timeout_sec:
            self._active_accum += gap
        self._last_active = now

    def composer_focus(self) -> None:
        self._composer_started = time.perf_counter()

    def composer_to_send_ms(self) -> float:
        if self._composer_started is None:
            return 0.0
        return (time.perf_counter() - self._composer_started) * 1000.0

    def note_idle_before_turn(self) -> None:
        gap = time.monotonic() - self._last_active
        self._idle_before_turn = gap if gap > self.idle_timeout_sec else 0.0

    def time_on_task_sec(self) -> float:
        self.mark_active()
        return self._active_accum

    def idle_before_turn_sec(self) -> float:
        return self._idle_before_turn
