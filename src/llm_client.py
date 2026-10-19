"""
llm_client.py
=============
Unified LLM client for the ATBP project.

Supports two backends, controlled by LLM_BACKEND in config/config.py:
  - "ollama"  : Local Ollama via OpenAI-compatible API (default)
  - "gemini"  : Google Gemini via google-genai SDK

Usage:
    from src.llm_client import call_llm

    text, prompt_tokens, completion_tokens = call_llm(system_prompt, user_content)
"""

import os
from config.config import (
    LLM_BACKEND,
    MODEL_NAME,
    GEMINI_MODEL_NAME,
    OPENAI_MODEL_NAME,
    MAX_TOKENS,
    TEMPERATURE,
)

# ---------------------------------------------------------------------------
# Ollama / OpenAI-compatible client
# ---------------------------------------------------------------------------
_ollama_client = None

def _get_ollama_client():
    global _ollama_client
    if _ollama_client is None:
        from openai import OpenAI
        _ollama_client = OpenAI(
            base_url="http://localhost:11434/v1",
            api_key="ollama",
            timeout=180.0,
        )
    return _ollama_client


def _call_ollama(system_prompt: str, user_content: str) -> tuple[str, int, int]:
    client = _get_ollama_client()
    response = client.chat.completions.create(
        model=MODEL_NAME,
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_content},
        ],
    )
    text = response.choices[0].message.content or ""
    usage = response.usage
    prompt_tokens     = usage.prompt_tokens     if usage else 0
    completion_tokens = usage.completion_tokens if usage else 0
    return text.strip(), prompt_tokens, completion_tokens


# ---------------------------------------------------------------------------
# Gemini client (new google-genai SDK)
# ---------------------------------------------------------------------------

# Models tried in order if the primary is overloaded (503)
_GEMINI_FALLBACK_MODELS = [
    GEMINI_MODEL_NAME,
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-3.1-flash-lite-preview",
]

def _call_gemini(system_prompt: str, user_content: str) -> tuple[str, int, int]:
    from google import genai
    from google.genai import types
    from google.genai.errors import ServerError

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "GEMINI_API_KEY is not set. "
            "Please add it to your .env file."
        )

    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=15000),  # 15s timeout — fail fast on 503
    )

    last_error = None
    for model in _GEMINI_FALLBACK_MODELS:
        try:
            print(f"[llm_client] Trying model: {model}")
            response = client.models.generate_content(
                model=model,
                contents=user_content,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=TEMPERATURE,
                    max_output_tokens=MAX_TOKENS,
                ),
                # Fail fast so we can try the next fallback model quickly
                # (http_options not supported here; handled by short client timeout)
            )
            text = response.text or ""
            usage = getattr(response, "usage_metadata", None)
            prompt_tokens     = getattr(usage, "prompt_token_count",     0) if usage else 0
            completion_tokens = getattr(usage, "candidates_token_count", 0) if usage else 0
            print(f"[llm_client] Success with model: {model}")
            return text.strip(), prompt_tokens, completion_tokens

        except ServerError as e:
            if "503" in str(e) or "UNAVAILABLE" in str(e):
                print(f"[llm_client] {model} unavailable, trying next...")
                last_error = e
                continue
            raise  # re-raise non-503 errors immediately
        except Exception as e:
            if "NOT_FOUND" in str(e) or "404" in str(e):
                print(f"[llm_client] {model} not found, trying next...")
                last_error = e
                continue
            raise

    raise RuntimeError(
        f"All Gemini models failed. Last error: {last_error}"
    )


# ---------------------------------------------------------------------------
# OpenAI client (ChatGPT, GPT-4o, etc.)
# ---------------------------------------------------------------------------

def _call_openai(system_prompt: str, user_content: str) -> tuple[str, int, int]:
    from openai import OpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "OPENAI_API_KEY is not set. "
            "Please add it to your .env file."
        )

    client = OpenAI(api_key=api_key)

    response = client.chat.completions.create(
        model=OPENAI_MODEL_NAME,
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    )
    text = response.choices[0].message.content or ""
    usage = response.usage
    prompt_tokens = usage.prompt_tokens if usage else 0
    completion_tokens = usage.completion_tokens if usage else 0
    return text.strip(), prompt_tokens, completion_tokens

def call_llm(system_prompt: str, user_content: str) -> tuple[str, int, int]:
    """
    Call the configured LLM backend.

    Returns:
        (text, prompt_tokens, completion_tokens)
    """
    backend = LLM_BACKEND.lower()

    if backend == "gemini":
        return _call_gemini(system_prompt, user_content)
    elif backend == "openai":
        return _call_openai(system_prompt, user_content)
    elif backend == "ollama":
        return _call_ollama(system_prompt, user_content)
    else:
        raise ValueError(
            f"Unknown LLM_BACKEND: '{LLM_BACKEND}'. "
            "Choose 'ollama', 'gemini', or 'openai' in config/config.py."
        )
