import os

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Backend selection
# Set LLM_BACKEND to "gemini", "openai", or "ollama" for local.
# ---------------------------------------------------------------------------
LLM_BACKEND = "openai"   # "ollama" | "gemini" | "openai"

# Ollama (local) settings
API_KEY    = "ollama"
MODEL_NAME = "qwen2.5:7b"

# Gemini settings
GEMINI_API_KEY    = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL_NAME = "gemini-flash-latest"   # always resolves to latest available flash

# OpenAI settings
OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL_NAME = "gpt-4o-mini"   # gpt-4o-mini for cheap, gpt-4o for better

MAX_TOKENS  = 2048
TEMPERATURE = 0

# Recovery strategy parameters
VERIFICATION_THRESHOLD = 0.75  # τ: confidence threshold for claim acceptance
MAX_REGENERATIONS = 2          # A2: max full plan regenerations
MAX_REPAIR_ATTEMPTS = 2        # A3: repairs per claim (1 = no loop)

# Adaptive recovery (A4) parameters
ADAPTATION_MODE = "greedy"     # "greedy", "confidence_based", "dependency_based"


