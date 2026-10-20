"""
Unified Configuration Module for ATBP (Adaptive Targeted Backtracking Protocol)

This module provides auto-detection of LLM provider (OpenAI, Gemini, or local Ollama)
based on available API keys in the .env file. It loads environment variables using
python-dotenv and returns a single configuration object with all necessary settings.

Features:
    - Auto-detection of LLM provider based on .env variables
    - Fallback hierarchy: OpenAI → Gemini → Local Ollama
    - Comprehensive configuration for all three providers
    - Logging of active provider selection
    - Validation of required keys
    - Sensible defaults for model names and parameters

Typical usage:
    from config.config_unified import get_config
    config = get_config()
    print(f"Using provider: {config.api_provider}")
    print(f"Model: {config.model}")
"""

import os
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Literal

from dotenv import load_dotenv


# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


@dataclass
class ATBPConfig:
    """
    Unified configuration object for ATBP multi-agent pipeline.
    
    Attributes:
        api_provider (str): The LLM provider being used ("openai", "gemini", or "ollama")
        api_key (str): API key for the selected provider (empty string for local Ollama)
        base_url (str): Base URL for API calls (provider-specific endpoint)
        model (str): Model name/identifier for the selected provider
        
        tau (float): Confidence threshold (τ) for claim verification acceptance
        max_regenerations (int): Maximum full plan regenerations (A2 strategy)
        max_repair_attempts (int): Maximum repair attempts per claim (A3 strategy)
        
        temps (list[float]): Temperature values for regeneration attempts
        max_tokens (int): Maximum tokens for model outputs
        
    Example:
        config = get_config()
        assert config.api_provider in ["openai", "gemini", "ollama"]
        print(f"Using {config.model} from {config.api_provider}")
    """
    
    # Provider and authentication
    api_provider: Literal["openai", "gemini", "ollama"] = "ollama"
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    
    # Claim verification parameters
    tau: float = 0.80
    
    # Recovery strategy parameters
    max_regenerations: int = 3
    max_repair_attempts: int = 2
    
    # Generation parameters
    temps: list[float] = field(default_factory=lambda: [0.0, 0.7, 0.7])
    max_tokens: int = 2048
    base_seed: int = 42  # Seed for reproducibility
    
    # Caching parameters
    caching_enabled: bool = True  # Enable/disable deterministic disk caching


def _get_env_path() -> Path:
    """
    Locate the .env file in the project root.
    
    Returns:
        Path: Absolute path to the .env file
        
    Raises:
        FileNotFoundError: If .env file cannot be found
    """
    # Start from the config module directory and walk up
    config_dir = Path(__file__).parent
    project_root = config_dir.parent
    env_file = project_root / ".env"
    
    if not env_file.exists():
        raise FileNotFoundError(
            f".env file not found at {env_file}. "
            f"Please create a .env file in the project root ({project_root})."
        )
    
    return env_file


def _detect_provider() -> tuple[Literal["openai", "gemini", "ollama"], str]:
    """
    Auto-detect the LLM provider based on available API keys.
    
    Detection order (fallback hierarchy):
        1. If OPENAI_API_KEY is present and non-empty → "openai"
        2. If GEMINI_API_KEY is present and non-empty → "gemini"
        3. Otherwise → "ollama" (local, requires no API key)
    
    Returns:
        tuple: (provider_name, api_key)
            - provider_name: "openai", "gemini", or "ollama"
            - api_key: API key string (empty for Ollama)
    
    Example:
        provider, key = _detect_provider()
        print(f"Detected provider: {provider}")
    """
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    
    if openai_key:
        logger.info("Auto-detected LLM provider: OpenAI (OPENAI_API_KEY found)")
        return "openai", openai_key
    elif gemini_key:
        logger.info("Auto-detected LLM provider: Gemini (GEMINI_API_KEY found, OpenAI not available)")
        return "gemini", gemini_key
    else:
        logger.info("Auto-detected LLM provider: Ollama (local, no API keys found)")
        return "ollama", ""


def _get_provider_config(
    provider: Literal["openai", "gemini", "ollama"],
    api_key: str
) -> tuple[str, str]:
    """
    Get provider-specific base_url and default model name.
    
    Args:
        provider: The LLM provider ("openai", "gemini", or "ollama")
        api_key: The API key for the provider (not used to determine defaults)
    
    Returns:
        tuple: (base_url, model_name)
            - base_url: API endpoint URL
            - model_name: Default model identifier for this provider
    
    Raises:
        ValueError: If provider is not recognized
    """
    if provider == "openai":
        return (
            "https://api.openai.com/v1",
            "gpt-3.5-turbo"
        )
    elif provider == "gemini":
        return (
            "https://generativelanguage.googleapis.com/v1beta/openai/",
            "gemini-2.0-flash"
        )
    elif provider == "ollama":
        return (
            "http://localhost:11434/v1",
            "llama3.2"
        )
    else:
        raise ValueError(
            f"Unknown provider: {provider}. "
            f"Must be one of: 'openai', 'gemini', 'ollama'"
        )


def get_config(
    env_path: Path = None,
    tau: float = 0.80,
    max_regenerations: int = 3,
    max_repair_attempts: int = 2,
    temps: list[float] = None,
    max_tokens: int = 2048,
    base_seed: int = 42,
    caching_enabled: bool = True
) -> ATBPConfig:
    """
    Load and validate configuration from .env, auto-detecting LLM provider.
    
    This function:
        1. Loads environment variables from .env file
        2. Auto-detects the best available LLM provider
        3. Validates that required API keys are present (if applicable)
        4. Returns a fully configured ATBPConfig instance
    
    Args:
        env_path (Path, optional): Path to .env file. If None, auto-detects from project root.
        tau (float): Verification confidence threshold (0.0-1.0). Default: 0.80
        max_regenerations (int): Maximum full plan regenerations (A2). Default: 3
        max_repair_attempts (int): Maximum repair attempts per claim (A3). Default: 2
        temps (list[float], optional): Temperature schedule for regenerations.
            Default: [0.0, 0.7, 0.7] (initial=deterministic, recoveries=stochastic)
        max_tokens (int): Maximum output tokens per LLM call. Default: 2048
        caching_enabled (bool): Enable deterministic disk caching in LLMClient. Default: True
    
    Returns:
        ATBPConfig: Fully configured object with provider, API key, base URL, model, and parameters
    
    Raises:
        FileNotFoundError: If .env file cannot be found
        ValueError: If required environment variables are missing
        
    Example:
        >>> config = get_config()
        >>> print(f"Provider: {config.api_provider}, Model: {config.model}")
        Provider: openai, Model: gpt-3.5-turbo
        >>> print(f"Verification threshold (τ): {config.tau}")
        Verification threshold (τ): 0.8
    """
    # Determine .env path
    if env_path is None:
        env_path = _get_env_path()
    else:
        env_path = Path(env_path)
    
    # Load .env file
    logger.info(f"Loading .env file from: {env_path}")
    load_dotenv(dotenv_path=env_path, override=False)
    
    # Auto-detect provider
    provider, api_key = _detect_provider()
    
    # Get provider-specific configuration
    base_url, model = _get_provider_config(provider, api_key)
    
    # Validate that Ollama is accessible if using local
    if provider == "ollama":
        logger.warning(
            "Using local Ollama provider. Ensure Ollama is running at http://localhost:11434"
        )
    
    # Set default temperatures if not provided
    if temps is None:
        temps = [0.0, 0.7, 0.7]
    
    # Create and return configuration object
    config = ATBPConfig(
        api_provider=provider,
        api_key=api_key,
        base_url=base_url,
        model=model,
        tau=tau,
        max_regenerations=max_regenerations,
        max_repair_attempts=max_repair_attempts,
        temps=temps,
        max_tokens=max_tokens,
        base_seed=base_seed,
        caching_enabled=caching_enabled
    )
    
    logger.info(
        f"Configuration loaded: provider={config.api_provider}, "
        f"model={config.model}, tau={config.tau}, "
        f"max_tokens={config.max_tokens}, caching={'enabled' if config.caching_enabled else 'disabled'}"
    )
    
    return config


if __name__ == "__main__":
    """
    Simple test to verify configuration loading and provider detection.
    
    Run with: python -m config.config_unified
    """
    try:
        config = get_config()
        print("\n" + "="*70)
        print("ATBP Unified Configuration Loaded Successfully")
        print("="*70)
        print(f"Provider:          {config.api_provider}")
        print(f"Model:             {config.model}")
        print(f"Base URL:          {config.base_url}")
        print(f"API Key Present:   {bool(config.api_key)}")
        print(f"\nVerification Parameters:")
        print(f"  Tau (τ):         {config.tau}")
        print(f"  Max Regenerations: {config.max_regenerations}")
        print(f"  Max Repair Attempts: {config.max_repair_attempts}")
        print(f"\nGeneration Parameters:")
        print(f"  Temperatures:    {config.temps}")
        print(f"  Max Tokens:      {config.max_tokens}")
        print("="*70 + "\n")
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        raise
