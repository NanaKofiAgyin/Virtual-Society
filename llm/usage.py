"""LLM call counting, token tracking, and sliding-window rate limiting (stdlib only)."""

from __future__ import annotations

import time
from collections import deque
from typing import Any, Callable


class UsageTracker:
    """Tracks local/mock LLM calls, token counts, and per-minute rate limits.

    Cost is always $0.00 because only free local (Ollama) or mock modes are used.
    """

    def __init__(self, clock: Callable[[], float] | None = None) -> None:
        """Initialize empty counters and a 60-second sliding call timestamp window."""
        self._clock: Callable[[], float] = clock if clock is not None else time.monotonic
        self._timestamps: deque[float] = deque()

        self.total_calls: int = 0
        self.mock_calls: int = 0
        self.ollama_calls: int = 0
        self.cache_hits: int = 0
        self.fallbacks: int = 0
        self.input_tokens: int = 0
        self.output_tokens: int = 0

    def _prune(self, now: float) -> None:
        """Drop call timestamps older than 60 seconds."""
        cutoff = now - 60.0
        while self._timestamps and self._timestamps[0] <= cutoff:
            self._timestamps.popleft()

    def record(
        self,
        mode: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        fallback: bool = False,
    ) -> None:
        """Record a completed LLM call and its token counts."""
        now = self._clock()
        self._prune(now)
        self._timestamps.append(now)

        self.total_calls += 1
        if mode == "mock":
            self.mock_calls += 1
        else:
            self.ollama_calls += 1
        if fallback:
            self.fallbacks += 1

        self.input_tokens += max(0, int(input_tokens))
        self.output_tokens += max(0, int(output_tokens))

    def record_cache_hit(self) -> None:
        """Record a response served from the in-memory cache."""
        self.cache_hits += 1

    def calls_last_minute(self) -> int:
        """Return the number of calls recorded within the last 60 seconds."""
        self._prune(self._clock())
        return len(self._timestamps)

    def seconds_until_slot(self, max_per_min: int) -> float:
        """Return seconds to wait before another call fits in `max_per_min`."""
        if max_per_min <= 0:
            return 0.0
        now = self._clock()
        self._prune(now)
        if len(self._timestamps) < max_per_min:
            return 0.0
        oldest = self._timestamps[0]
        return max(0.0, round(60.0 - (now - oldest), 4))

    def summary(self) -> dict[str, Any]:
        """Return a JSON-friendly summary of usage metrics (cost is always $0.0)."""
        return {
            "total_calls": self.total_calls,
            "mock_calls": self.mock_calls,
            "ollama_calls": self.ollama_calls,
            "cache_hits": self.cache_hits,
            "fallbacks": self.fallbacks,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.input_tokens + self.output_tokens,
            "calls_last_minute": self.calls_last_minute(),
            "cost_usd": 0.0,
        }
