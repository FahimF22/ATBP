"""
llm_client_unified.py
=====================
Unified LLM client for the ATBP project with retry logic, token tracking, and error handling.

This module provides a single LLMClient class that wraps the OpenAI SDK to support:
  - Multiple backends (OpenAI, Gemini, local Ollama) via OpenAI-compatible API
  - Retry logic with exponential backoff (2^attempt seconds: 2s, 4s, 8s)
  - Token usage tracking with safe fallback estimation
  - Comprehensive error handling and logging
  - Full type hints and docstrings

Usage:
    from config.config_unified import get_config
    from src.llm_client_unified import LLMClient

    config = get_config()
    client = LLMClient(config)
    
    response_text, usage_dict = client.call(
        prompt="Solve this problem...",
        system_prompt="You are a math solver.",
        temperature=0.7,
        max_tokens=2048
    )
    
    print(f"Response: {response_text}")
    print(f"Tokens used: {usage_dict}")
"""

import logging
import time
import sqlite3
import hashlib
import threading
import json
from typing import Tuple, Dict, Optional
from dataclasses import dataclass

from openai import (
    OpenAI,
    APIError,
    APIConnectionError,
    RateLimitError,
)

from config.config_unified import ATBPConfig


# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


@dataclass
class LLMClient:
    """
    Unified LLM client for the ATBP multi-agent pipeline.
    
    Supports OpenAI, Gemini, and local Ollama backends via OpenAI-compatible API.
    Includes retry logic with exponential backoff and safe token tracking.
    
    Attributes:
        config (ATBPConfig): Configuration object from config_unified.py
        _client (OpenAI): Internal OpenAI SDK client instance
        _max_retries (int): Maximum retry attempts (default: 3)
        _base_retry_wait (float): Initial retry wait in seconds (default: 2.0)
    
    Example:
        >>> config = get_config()
        >>> client = LLMClient(config)
        >>> text, usage = client.call("Tell me a joke", temperature=0.8)
        >>> print(usage)
        {'prompt_tokens': 5, 'completion_tokens': 15}
    """
    
    config: ATBPConfig
    _max_retries: int = 3
    _base_retry_wait: float = 2.0
    
    def __post_init__(self):
        """Initialize the OpenAI client with appropriate base_url and API key."""
        self._client = OpenAI(
            base_url=self.config.base_url,
            api_key=self.config.api_key if self.config.api_key else "ollama",
            timeout=180.0,
        )
        
        # Initialize cache
        self._cache_enabled = self.config.caching_enabled
        self._cache_db_path = ".atbp_llm_cache.sqlite"
        self._cache_lock = threading.Lock()
        
        if self._cache_enabled:
            self._init_cache_db()
        
        logger.info(
            f"LLMClient initialized for {self.config.api_provider} "
            f"({self.config.model}) at {self.config.base_url} | "
            f"Cache: {'enabled' if self._cache_enabled else 'disabled'}"
        )
    
    def _estimate_tokens(self, text: str) -> int:
        """
        Estimate token count based on word count (rough approximation).
        
        This is a fallback when the API does not return token usage.
        Uses rough heuristic: ~1.3 tokens per word for English text.
        
        Args:
            text (str): The text to estimate tokens for
        
        Returns:
            int: Estimated token count
        """
        words = len(text.split())
        return max(1, int(words * 1.3))
    
    def _init_cache_db(self) -> None:
        """Initialize SQLite cache database if not already initialized."""
        try:
            conn = sqlite3.connect(self._cache_db_path, timeout=10.0, check_same_thread=False)
            cursor = conn.cursor()
            
            # Create cache table if not exists
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS llm_cache (
                    cache_key TEXT PRIMARY KEY,
                    api_provider TEXT,
                    model TEXT,
                    response_text TEXT,
                    prompt_tokens INTEGER,
                    completion_tokens INTEGER,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.commit()
            conn.close()
            
            logger.debug(f"Cache database initialized: {self._cache_db_path}")
        except Exception as e:
            logger.warning(f"Failed to initialize cache database: {e}. Caching disabled.")
            self._cache_enabled = False
    
    def _compute_cache_key(self, prompt: str, temperature: float, max_tokens: int, seed: Optional[int]) -> str:
        """
        Compute deterministic SHA-256 cache key from inputs.
        
        Components: provider, model, prompt, temperature, max_tokens, seed
        All components are included so identical inputs produce identical keys.
        
        Args:
            prompt (str): The prompt text
            temperature (float): Temperature setting
            max_tokens (int): Max tokens setting
            seed (Optional[int]): Random seed (or None)
        
        Returns:
            str: SHA-256 hex digest for cache key
        """
        key_data = f"{self.config.api_provider}|{self.config.model}|{prompt}|{temperature}|{max_tokens}|{seed or 'none'}"
        return hashlib.sha256(key_data.encode("utf-8")).hexdigest()
    
    def _get_cached_response(self, cache_key: str) -> Optional[Tuple[str, Dict[str, int]]]:
        """
        Retrieve cached response if available.
        
        Args:
            cache_key (str): Cache key computed from inputs
        
        Returns:
            Tuple[response_text, usage_dict] if found, None otherwise
        """
        if not self._cache_enabled:
            return None
        
        try:
            with self._cache_lock:
                conn = sqlite3.connect(self._cache_db_path, timeout=10.0, check_same_thread=False)
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT response_text, prompt_tokens, completion_tokens
                    FROM llm_cache
                    WHERE cache_key = ?
                """, (cache_key,))
                
                row = cursor.fetchone()
                conn.close()
                
                if row:
                    response_text, prompt_tokens, completion_tokens = row
                    usage_dict = {
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens
                    }
                    logger.debug(f"Cache hit for key {cache_key[:8]}...")
                    return response_text, usage_dict
                
                return None
        except Exception as e:
            logger.warning(f"Cache retrieval error: {e}")
            return None
    
    def _store_cached_response(self, cache_key: str, response_text: str, 
                              prompt_tokens: int, completion_tokens: int) -> None:
        """Store response in cache."""
        if not self._cache_enabled:
            return
        
        try:
            with self._cache_lock:
                conn = sqlite3.connect(self._cache_db_path, timeout=10.0, check_same_thread=False)
                cursor = conn.cursor()
                
                cursor.execute("""
                    INSERT OR REPLACE INTO llm_cache 
                    (cache_key, api_provider, model, response_text, prompt_tokens, completion_tokens)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (cache_key, self.config.api_provider, self.config.model, 
                      response_text, prompt_tokens, completion_tokens))
                
                conn.commit()
                conn.close()
                
                logger.debug(f"Cached response for key {cache_key[:8]}...")
        except Exception as e:
            logger.warning(f"Cache storage error: {e}")
    
    def _get_usage_dict(
        self,
        response_text: str,
        prompt: str,
        api_usage
    ) -> Dict[str, int]:
        """
        Extract or estimate token usage from API response.
        
        If the API returns usage statistics, use those. Otherwise, fall back
        to estimation based on prompt and response lengths.
        
        Args:
            response_text (str): The response text from the LLM
            prompt (str): The original prompt sent to the LLM
            api_usage: The usage object from the API response (may be None)
        
        Returns:
            Dict[str, int]: Dictionary with keys "prompt_tokens" and "completion_tokens"
        """
        if api_usage is not None:
            prompt_tokens = getattr(api_usage, "prompt_tokens", None)
            completion_tokens = getattr(api_usage, "completion_tokens", None)
            
            if prompt_tokens is not None and completion_tokens is not None:
                return {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                }
        
        # Fallback: estimate based on token counts
        estimated_prompt_tokens = self._estimate_tokens(prompt)
        estimated_completion_tokens = self._estimate_tokens(response_text)
        
        logger.warning(
            f"API did not return usage stats. Using estimates: "
            f"prompt={estimated_prompt_tokens}, completion={estimated_completion_tokens}"
        )
        
        return {
            "prompt_tokens": estimated_prompt_tokens,
            "completion_tokens": estimated_completion_tokens,
        }
    
    def call(
        self,
        prompt: str,
        system_prompt: str = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        seed: int = None,
    ) -> Tuple[str, Dict[str, int]]:
        """
        Call the LLM with caching, retry logic and exponential backoff.
        
        Attempts cache retrieval first. On cache miss, makes API call with retries,
        stores result, and returns.
        
        Automatically retries on transient errors (rate limits, connection issues)
        with exponential backoff: 2s, 4s, 8s. Logs each retry attempt and full
        error context on final failure.
        
        Args:
            prompt (str): The user prompt/query to send to the LLM
            system_prompt (str, optional): System message to guide the LLM behavior.
                Default: None (no system prompt)
            temperature (float): Sampling temperature (0.0 = deterministic, 1.0+ = stochastic).
                Default: 0.7
            max_tokens (int): Maximum output tokens. Default: 2048
            seed (int, optional): Random seed for reproducibility (if supported by model).
                Default: None
        
        Returns:
            Tuple[str, Dict[str, int]]: A tuple of:
                - response_text (str): The LLM's response text (stripped of whitespace)
                - usage_dict (Dict[str, int]): Token usage with keys "prompt_tokens" 
                  and "completion_tokens"
        
        Raises:
            APIError: If all retry attempts fail (after 3 attempts)
            APIConnectionError: If connection cannot be established after retries
            RateLimitError: If rate limited even after retries (unlikely with backoff)
            Exception: For non-retryable errors (invalid request, auth failure, etc.)
        
        Example:
            >>> config = get_config()
            >>> client = LLMClient(config)
            >>> text, usage = client.call(
            ...     prompt="What is 2 + 2?",
            ...     system_prompt="You are a math tutor.",
            ...     temperature=0.0,
            ...     max_tokens=100
            ... )
            >>> print(f"Response: {text}")
            >>> print(f"Tokens: {usage['prompt_tokens']}")
            
        Retry Behavior:
            - RateLimitError, APIConnectionError, APIError → retry with backoff
            - Other exceptions (auth, validation) → raise immediately
            - After max retries, raises the original exception with full context
        """
        # Compute cache key
        cache_key = self._compute_cache_key(prompt, temperature, max_tokens, seed)
        
        # Check cache
        cached_result = self._get_cached_response(cache_key)
        if cached_result is not None:
            response_text, usage_dict = cached_result
            return response_text, usage_dict
        
        # Cache miss; proceed with API call
        if system_prompt is None:
            system_prompt = ""
        
        full_prompt = prompt
        messages = []
        
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        messages.append({"role": "user", "content": prompt})
        
        # Prepare API call parameters
        api_params = {
            "model": self.config.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        
        # Only include seed if provided (not all models support it)
        if seed is not None:
            api_params["seed"] = seed
        
        # Retry loop with exponential backoff
        last_exception = None
        
        for attempt in range(self._max_retries):
            try:
                logger.debug(f"LLM call attempt {attempt + 1}/{self._max_retries}")
                
                response = self._client.chat.completions.create(**api_params)
                
                # Extract response text
                response_text = response.choices[0].message.content or ""
                response_text = response_text.strip()
                
                # Extract or estimate token usage
                usage_dict = self._get_usage_dict(
                    response_text,
                    full_prompt,
                    response.usage
                )
                
                # Store in cache BEFORE returning
                self._store_cached_response(
                    cache_key, response_text,
                    usage_dict.get("prompt_tokens", 0),
                    usage_dict.get("completion_tokens", 0)
                )
                
                logger.debug(
                    f"LLM call succeeded on attempt {attempt + 1}. "
                    f"Usage: {usage_dict}"
                )
                
                return response_text, usage_dict
                
            except (RateLimitError, APIConnectionError, APIError) as e:
                last_exception = e
                
                # Check if this is the last attempt
                if attempt == self._max_retries - 1:
                    # Final attempt failed; raise with context
                    logger.error(
                        f"LLM call failed after {self._max_retries} attempts. "
                        f"Last error: {type(e).__name__}: {str(e)}"
                    )
                    raise
                
                # Calculate backoff: 2^attempt seconds
                wait_time = self._base_retry_wait ** (attempt + 1)
                
                logger.warning(
                    f"LLM call failed on attempt {attempt + 1}/{self._max_retries}. "
                    f"Error: {type(e).__name__}: {str(e)}. "
                    f"Retrying in {wait_time:.1f}s..."
                )
                
                time.sleep(wait_time)
            
            except Exception as e:
                # Non-retryable error; raise immediately
                logger.error(
                    f"Non-retryable LLM error on attempt {attempt + 1}: "
                    f"{type(e).__name__}: {str(e)}"
                )
                raise
        
        # This should not be reached due to raises in the loop, but for safety:
        if last_exception is not None:
            logger.error(
                f"LLM call exhausted all {self._max_retries} retry attempts"
            )
            raise last_exception
        
        raise RuntimeError("Unexpected state: no exception raised but no response returned")
