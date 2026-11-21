"""Unit tests for the `llm` package (mock mode, JSON repair, retries, rate limits)."""

from __future__ import annotations

import json
import urllib.error
from typing import Any

from llm import LLMClient, UsageTracker, extract_json


class _FakeHTTPResponse:
    """Minimal context-manager response stub for `urllib.request.urlopen`."""

    def __init__(self, content: str, in_tok: int = 20, out_tok: int = 10) -> None:
        self._payload = json.dumps(
            {
                "message": {"role": "assistant", "content": content},
                "prompt_eval_count": in_tok,
                "eval_count": out_tok,
            }
        ).encode("utf-8")

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> _FakeHTTPResponse:
        return self

    def __exit__(self, *args: Any) -> None:
        return None


def test_mock_mode_makes_no_network_call() -> None:
    """Default mock mode never touches the network and populates required keys."""
    def forbid_network(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("Network must not be called in mock mode")

    client = LLMClient(mode="mock", urlopen_fn=forbid_network)
    reply = client.ask("sys", "Say hello", json=True, required=("speech", "mood"))

    assert isinstance(reply, dict)
    assert reply["speech"] == "mock_speech"
    assert reply["mood"] == "mock_mood"
    assert "_fallback" not in reply
    assert client.usage.summary()["mock_calls"] == 1
    assert client.usage.summary()["cost_usd"] == 0.0

    # Plain string mode also works with zero network calls
    text = client.ask("sys", "Plan my day", json=False)
    assert isinstance(text, str) and len(text) > 0


def test_json_repair_strips_fences_and_prose() -> None:
    """extract_json handles markdown code fences and surrounding prose."""
    fenced = 'Sure! Here is your JSON:\n```json\n{"speech": "Good morning!", "plan": "farm"}\n```\nHope that helps!'
    assert extract_json(fenced) == {"speech": "Good morning!", "plan": "farm"}

    messy = 'Thinking... {"action": "talk", "target": "Ada"} done.'
    assert extract_json(messy) == {"action": "talk", "target": "Ada"}

    assert extract_json("not json at all") is None


def test_valid_ollama_path_tiers_and_cache() -> None:
    """Ollama mode maps main/cheap tiers, parses JSON, tracks tokens, and caches."""
    seen_models: list[str] = []

    def fake_urlopen(req: Any, timeout: float = 30.0) -> _FakeHTTPResponse:
        body = json.loads(req.data.decode("utf-8"))
        seen_models.append(body["model"])
        return _FakeHTTPResponse('```json\n{"speech": "Hello friend!"}\n```', in_tok=30, out_tok=12)

    client = LLMClient(
        mode="ollama",
        model_main="llama3.2",
        model_cheap="llama3.2:1b",
        enable_cache=True,
        urlopen_fn=fake_urlopen,
        sleep_fn=lambda _: None,
    )

    res1 = client.ask("sys", "greet", json=True, model_tier="main", required=("speech",))
    res2 = client.ask("sys", "greet", json=True, model_tier="main", required=("speech",))
    res3 = client.ask("sys", "greet", json=True, model_tier="cheap", required=("speech",))

    assert res1 == {"speech": "Hello friend!"}
    assert res2 == res1
    assert res3 == {"speech": "Hello friend!"}
    assert seen_models == ["llama3.2", "llama3.2:1b"]
    summary = client.usage.summary()
    assert summary["ollama_calls"] == 2
    assert summary["cache_hits"] == 1
    assert summary["input_tokens"] == 60
    assert summary["output_tokens"] == 24
    assert summary["cost_usd"] == 0.0


def test_bad_json_retries_once_then_returns_fallback() -> None:
    """Malformed JSON triggers one 'valid JSON only' retry before returning _fallback."""
    prompts_sent: list[str] = []

    def bad_json_urlopen(req: Any, timeout: float = 30.0) -> _FakeHTTPResponse:
        body = json.loads(req.data.decode("utf-8"))
        prompts_sent.append(body["messages"][1]["content"])
        return _FakeHTTPResponse("I forgot to format as JSON sorry")

    client = LLMClient(
        mode="ollama",
        enable_cache=False,
        urlopen_fn=bad_json_urlopen,
        sleep_fn=lambda _: None,
    )
    res = client.ask("sys", "decide", json=True, required=("speech",))

    assert isinstance(res, dict)
    assert res["_fallback"] is True
    assert "speech" in res
    assert len(prompts_sent) == 2
    assert "valid JSON only" in prompts_sent[1]


def test_network_error_retries_3_times_with_backoff_and_never_raises() -> None:
    """Network failures retry 3 times with exponential backoff, then return fallback."""
    sleeps: list[float] = []
    attempts = 0

    def failing_urlopen(req: Any, timeout: float = 30.0) -> Any:
        nonlocal attempts
        attempts += 1
        raise urllib.error.URLError("connection refused")

    client = LLMClient(
        mode="ollama",
        enable_cache=False,
        urlopen_fn=failing_urlopen,
        sleep_fn=sleeps.append,
    )
    res = client.ask("sys", "hello", json=True, required=("speech",))

    assert attempts == 3
    assert sleeps == [0.5, 1.0]
    assert isinstance(res, dict) and res["_fallback"] is True


def test_usage_rate_limit_math_and_waiting() -> None:
    """UsageTracker computes sliding-window call counts and wait times accurately."""
    now = [100.0]
    tracker = UsageTracker(clock=lambda: now[0])

    tracker.record("ollama", input_tokens=10, output_tokens=5)
    now[0] = 110.0
    tracker.record("ollama", input_tokens=10, output_tokens=5)

    assert tracker.calls_last_minute() == 2
    assert tracker.seconds_until_slot(max_per_min=5) == 0.0
    # At t=110 with oldest at t=100, slot frees at t=160 -> 50s wait
    assert tracker.seconds_until_slot(max_per_min=2) == 50.0

    # Advance past t=160 -> first call expires from the 60s window
    now[0] = 161.0
    assert tracker.calls_last_minute() == 1
    assert tracker.seconds_until_slot(max_per_min=2) == 0.0
