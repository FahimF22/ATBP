"""
LLM client for ATBP.

    from src.llm_client import call_llm, track_usage

    with track_usage() as usage:
        text, prompt_tokens, completion_tokens = call_llm(system, user)
    print(usage)   # calls, tokens, llm_seconds, cache_hits

Default backend is a local Ollama server (free). Calls are cached on disk,
keyed by everything that affects the output. A cached call still adds its
original tokens and compute time to the usage counters, so cost numbers are
the same whether or not the cache was hit.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time
from contextlib import contextmanager

from config import config as cfg


# ---------------------------------------------------------------------------
# Usage tracking
# ---------------------------------------------------------------------------

# Per-thread, so parallel workers (--workers) each count only their own calls.
_local = threading.local()


def _stack() -> list[dict]:
    if not hasattr(_local, "usage_stack"):
        _local.usage_stack = []
    return _local.usage_stack


def _new_usage() -> dict:
    return {
        "calls": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "llm_seconds": 0.0,
        "cache_hits": 0,
    }


@contextmanager
def track_usage():
    """Collect usage of every LLM call made inside the block (nesting is fine)."""
    usage = _new_usage()
    _stack().append(usage)
    try:
        yield usage
    finally:
        _stack().remove(usage)
        usage["llm_seconds"] = round(usage["llm_seconds"], 3)


def _record(prompt_tokens, completion_tokens, seconds, cache_hit):
    for usage in _stack():
        usage["calls"] += 1
        usage["prompt_tokens"] += prompt_tokens
        usage["completion_tokens"] += completion_tokens
        usage["llm_seconds"] += seconds
        usage["cache_hits"] += int(cache_hit)


# ---------------------------------------------------------------------------
# Disk cache
# ---------------------------------------------------------------------------

_db = None
_db_lock = threading.Lock()


def _cache():
    """Shared SQLite connection. Callers must hold _db_lock."""
    global _db
    if _db is None:
        os.makedirs(os.path.dirname(cfg.CACHE_PATH) or ".", exist_ok=True)
        _db = sqlite3.connect(cfg.CACHE_PATH, check_same_thread=False)
        _db.execute(
            "CREATE TABLE IF NOT EXISTS calls ("
            "key TEXT PRIMARY KEY, text TEXT, prompt_tokens INTEGER, "
            "completion_tokens INTEGER, seconds REAL)"
        )
        _db.commit()
    return _db


def _cache_key(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


# ---------------------------------------------------------------------------
# Backends
# ---------------------------------------------------------------------------

_http = None
_openai_clients: dict = {}
_client_lock = threading.Lock()


def _client():
    global _http
    with _client_lock:
        if _http is None:
            import httpx

            _http = httpx.Client(timeout=600.0)
    return _http


def _openai_client(base_url, api_key):
    """One reusable client per endpoint (keeps connections open between calls)."""
    from openai import OpenAI

    with _client_lock:
        key = (base_url, api_key)
        if key not in _openai_clients:
            _openai_clients[key] = OpenAI(base_url=base_url or None,
                                          api_key=api_key or "none",
                                          timeout=120.0, max_retries=0)
        return _openai_clients[key]


def _call_ollama(system_prompt, user_content, temperature, seed, schema, model):
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "stream": False,
        "keep_alive": cfg.KEEP_ALIVE,
        "options": {
            "temperature": temperature,
            "seed": seed,
            "num_ctx": cfg.NUM_CTX,
            "num_predict": cfg.MAX_TOKENS,
        },
    }
    if schema is not None:
        body["format"] = schema
    resp = _client().post(f"{cfg.OLLAMA_URL}/api/chat", json=body)
    resp.raise_for_status()
    data = resp.json()
    text = (data.get("message") or {}).get("content", "") or ""
    return (
        text.strip(),
        int(data.get("prompt_eval_count") or 0),
        int(data.get("eval_count") or 0),
    )


def _strict(schema):
    """Copy of a JSON schema in the form OpenAI's strict mode requires: every
    object lists all its properties as required and allows no others."""
    if isinstance(schema, list):
        return [_strict(s) for s in schema]
    if not isinstance(schema, dict):
        return schema
    out = {k: _strict(v) for k, v in schema.items()}
    if out.get("type") == "object" and "properties" in out:
        out["additionalProperties"] = False
        out["required"] = list(out["properties"])
    return out


def _call_openai_compatible(system_prompt, user_content, temperature, seed,
                            schema, model, base_url, api_key):
    client = _openai_client(base_url, api_key)
    kwargs = {}
    if schema is not None and cfg.LLM_BACKEND.lower() == "openai":
        # Strict structured outputs: the reply must match the schema exactly.
        # (Plain JSON mode lets the model invent its own field names.)
        kwargs["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "response", "strict": True, "schema": _strict(schema)},
        }
    elif schema is not None:
        # Other OpenAI-style servers: plain JSON mode, which refuses requests
        # whose messages never say "JSON".
        kwargs["response_format"] = {"type": "json_object"}
        if "json" not in (system_prompt + user_content).lower():
            system_prompt += "\n\nRespond with a JSON object only."
    response = client.chat.completions.create(
        model=model,
        temperature=temperature,
        seed=seed,
        max_tokens=cfg.MAX_TOKENS,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        **kwargs,
    )
    text = response.choices[0].message.content or ""
    usage = response.usage
    return (
        text.strip(),
        usage.prompt_tokens if usage else 0,
        usage.completion_tokens if usage else 0,
    )


def _call_gemini(system_prompt, user_content, temperature):
    from google import genai
    from google.genai import types

    if not cfg.GEMINI_API_KEY:
        raise EnvironmentError("GEMINI_API_KEY is not set.")
    client = genai.Client(api_key=cfg.GEMINI_API_KEY)
    response = client.models.generate_content(
        model=cfg.GEMINI_MODEL_NAME,
        contents=user_content,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=temperature,
            max_output_tokens=cfg.MAX_TOKENS,
        ),
    )
    usage = getattr(response, "usage_metadata", None)
    return (
        (response.text or "").strip(),
        getattr(usage, "prompt_token_count", 0) if usage else 0,
        getattr(usage, "candidates_token_count", 0) if usage else 0,
    )


def _dispatch(system_prompt, user_content, temperature, seed, schema):
    backend = cfg.LLM_BACKEND.lower()
    if backend == "ollama":
        return _call_ollama(system_prompt, user_content, temperature, seed,
                            schema, cfg.MODEL_NAME)
    if backend == "openai_compatible":
        return _call_openai_compatible(system_prompt, user_content, temperature,
                                       seed, schema, cfg.MODEL_NAME,
                                       cfg.BASE_URL, cfg.API_KEY)
    if backend == "openai":
        return _call_openai_compatible(system_prompt, user_content, temperature,
                                       seed, schema, cfg.OPENAI_MODEL_NAME,
                                       "", cfg.OPENAI_API_KEY)
    if backend == "gemini":
        return _call_gemini(system_prompt, user_content, temperature)
    raise ValueError(f"Unknown backend: {cfg.LLM_BACKEND}")


def model_id() -> str:
    """Name of the model actually used, for logging."""
    backend = cfg.LLM_BACKEND.lower()
    if backend == "openai":
        return cfg.OPENAI_MODEL_NAME
    if backend == "gemini":
        return cfg.GEMINI_MODEL_NAME
    return cfg.MODEL_NAME


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def call_llm(
    system_prompt: str,
    user_content: str,
    temperature: float | None = None,
    seed: int | None = None,
    schema: dict | None = None,
    retries: int = 6,
) -> tuple[str, int, int]:
    """
    Call the configured model.

    temperature: defaults to cfg.TEMPERATURE (0).
    seed: sampling seed; defaults to cfg.BASE_SEED.
    schema: optional JSON schema; Ollama then constrains the output to it.

    Returns (text, prompt_tokens, completion_tokens).
    """
    if temperature is None:
        temperature = cfg.TEMPERATURE
    if seed is None:
        seed = cfg.BASE_SEED

    payload = {
        "backend": cfg.LLM_BACKEND,
        "model": model_id(),
        "num_ctx": cfg.NUM_CTX,
        "max_tokens": cfg.MAX_TOKENS,
        "system": system_prompt,
        "user": user_content,
        "temperature": temperature,
        "seed": seed,
        "schema": schema,
    }
    if schema is not None and cfg.LLM_BACKEND.lower() == "openai":
        payload["json_mode"] = "strict"   # replies saved before strict mode are not reused
    key = _cache_key(payload)

    if cfg.USE_CACHE:
        with _db_lock:
            row = _cache().execute(
                "SELECT text, prompt_tokens, completion_tokens, seconds "
                "FROM calls WHERE key = ?",
                (key,),
            ).fetchone()
        if row is not None:
            _record(row[1], row[2], row[3], cache_hit=True)
            return row[0], row[1], row[2]

    last_error = None
    text = None
    for attempt in range(retries):
        try:
            start = time.time()
            text, pt, ct = _dispatch(system_prompt, user_content,
                                     temperature, seed, schema)
            seconds = time.time() - start
            break
        except Exception as e:  # network hiccup, rate limit, model loading
            last_error = e
            if type(e).__name__ in ("AuthenticationError", "PermissionDeniedError",
                                    "NotFoundError", "BadRequestError"):
                break  # retrying will not help
            time.sleep(min(60, 2 ** (attempt + 1)))
    if text is None:
        raise RuntimeError(f"LLM call failed: {last_error}")

    _record(pt, ct, seconds, cache_hit=False)
    if cfg.USE_CACHE:
        with _db_lock:
            _cache().execute(
                "INSERT OR REPLACE INTO calls VALUES (?, ?, ?, ?, ?)",
                (key, text, pt, ct, seconds),
            )
            _cache().commit()
    return text, pt, ct


def call_llm_json(system_prompt, user_content, schema, **kwargs):
    """Call with a JSON schema and parse the result (with a lenient fallback)."""
    text, pt, ct = call_llm(system_prompt, user_content, schema=schema, **kwargs)
    return parse_json(text)


def parse_json(text: str):
    import re

    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for pattern in (r"\{[\s\S]*\}", r"\[[\s\S]*\]"):
        match = re.search(pattern, text)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                continue
    raise ValueError(f"Could not parse JSON from model output: {text[:200]}")
