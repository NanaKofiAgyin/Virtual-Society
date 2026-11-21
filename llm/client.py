"""Free local LLM client supporting `mock` (default) and local `ollama` via urllib."""

from __future__ import annotations

import json as json_lib
import re
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Sequence

from config import settings
from llm.usage import UsageTracker

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


def extract_json(raw: str) -> dict[str, Any] | None:
    """Strip markdown fences and extract a JSON object from messy model output."""
    text = raw.strip()
    if not text:
        return None

    fence_match = _FENCE_RE.search(text)
    if fence_match:
        text = fence_match.group(1).strip()

    for candidate in (text, _slice_braces(text)):
        if not candidate:
            continue
        try:
            parsed = json_lib.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json_lib.JSONDecodeError:
            continue
    return None


def _slice_braces(text: str) -> str:
    """Return the substring from the first '{' to the last '}' if present."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return ""
    return text[start : end + 1]


def _estimate_tokens(text: str) -> int:
    """Rough stdlib token estimate (~4 characters per token)."""
    return max(1, len(text) // 4) if text else 0


class LLMClient:
    """Provider-agnostic local LLM wrapper that never raises from `ask()`."""

    def __init__(
        self,
        mode: str | None = None,
        base_url: str | None = None,
        model_main: str | None = None,
        model_cheap: str | None = None,
        max_calls_per_minute: int | None = None,
        enable_cache: bool = True,
        timeout: float = 30.0,
        usage: UsageTracker | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        urlopen_fn: Callable[..., Any] = urllib.request.urlopen,
    ) -> None:
        """Configure client from explicit args or `config.settings`."""
        self.mode = (mode or settings.llm_mode).strip().lower()
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.model_main = model_main or settings.ollama_model_main
        self.model_cheap = model_cheap or settings.ollama_model_cheap
        self.max_calls_per_minute = (
            settings.max_calls_per_minute
            if max_calls_per_minute is None
            else max_calls_per_minute
        )
        self.enable_cache = enable_cache
        self.timeout = timeout
        self.usage = usage if usage is not None else UsageTracker()
        self._sleep = sleep_fn
        self._urlopen = urlopen_fn
        self._cache: dict[tuple[Any, ...], dict[str, Any] | str] = {}

    def is_live(self) -> bool:
        """Return True when backed by a live local model (Ollama), False in mock mode."""
        return self.mode != "mock"

    def _resolve_model(self, model_tier: str) -> str:
        """Map `main` or `cheap` tier to the configured Ollama model name."""
        return self.model_cheap if model_tier == "cheap" else self.model_main

    def _fallback_dict(self, required: Sequence[str], reason: str) -> dict[str, Any]:
        """Build a safe fallback dictionary containing `_fallback: True` and required keys."""
        result: dict[str, Any] = {"_fallback": True, "_reason": reason}
        for key in required:
            result.setdefault(key, "")
        return result

    def _mock_reply(self, user: str, want_json: bool, required: Sequence[str]) -> dict[str, Any] | str:
        """Generate a deterministic mock response without touching the network."""
        self.usage.record("mock", input_tokens=_estimate_tokens(user), output_tokens=8)
        if not want_json:
            return f"[mock] {user[:60]}".strip()
        data: dict[str, Any] = {key: f"mock_{key}" for key in required}
        if not data:
            data["response"] = "ok"
        return data

    def _post_ollama(self, model: str, system: str, user: str) -> tuple[str, int, int]:
        """POST to Ollama `/api/chat` with 3 retries and exponential backoff."""
        url = f"{self.base_url}/api/chat"
        payload = json_lib.dumps(
            {
                "model": model,
                "stream": False,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            }
        ).encode("utf-8")

        last_err: Exception | None = None
        for attempt in range(3):
            wait = self.usage.seconds_until_slot(self.max_calls_per_minute)
            if wait > 0.0:
                self._sleep(wait)
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with self._urlopen(req, timeout=self.timeout) as resp:
                    body = json_lib.loads(resp.read().decode("utf-8"))
                content = str(body.get("message", {}).get("content", ""))
                in_tok = int(body.get("prompt_eval_count", _estimate_tokens(system + user)))
                out_tok = int(body.get("eval_count", _estimate_tokens(content)))
                self.usage.record("ollama", input_tokens=in_tok, output_tokens=out_tok)
                return content, in_tok, out_tok
            except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
                last_err = exc
                if attempt < 2:
                    self._sleep(0.5 * (2**attempt))

        raise RuntimeError(f"Ollama request failed after 3 attempts: {last_err}")

    def ask(
        self,
        system: str,
        user: str,
        json: bool = True,
        model_tier: str = "main",
        required: Sequence[str] = (),
    ) -> dict[str, Any] | str:
        """Query the configured LLM safely; never raises on error."""
        cache_key = (self.mode, model_tier, json, tuple(required), system, user)
        if self.enable_cache and cache_key in self._cache:
            self.usage.record_cache_hit()
            return self._cache[cache_key]

        try:
            if self.mode == "mock":
                result = self._mock_reply(user, want_json=json, required=required)
                if self.enable_cache:
                    self._cache[cache_key] = result
                return result

            model = self._resolve_model(model_tier)
            raw_text, _, _ = self._post_ollama(model, system, user)
            if not json:
                if self.enable_cache:
                    self._cache[cache_key] = raw_text
                return raw_text

            parsed = extract_json(raw_text)
            if parsed is not None and all(k in parsed for k in required):
                if self.enable_cache:
                    self._cache[cache_key] = parsed
                return parsed

            # Retry once with an explicit "valid JSON only" reminder
            keys_hint = f" Required keys: {', '.join(required)}." if required else ""
            reminder = f"{user}\n\nIMPORTANT: Reply with valid JSON only, no extra text.{keys_hint}"
            retry_text, _, _ = self._post_ollama(model, system, reminder)
            parsed = extract_json(retry_text)
            if parsed is not None and all(k in parsed for k in required):
                if self.enable_cache:
                    self._cache[cache_key] = parsed
                return parsed

            self.usage.fallbacks += 1
            return self._fallback_dict(required, reason="invalid_json")
        except Exception as exc:  # noqa: BLE001 — ask() must never crash the simulation
            self.usage.fallbacks += 1
            return self._fallback_dict(required, reason=str(exc)) if json else ""
