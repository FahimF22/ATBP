import os

from dotenv import load_dotenv

load_dotenv()

# Ollama runs locally, so no OpenAI API key is required.
API_KEY = "ollama"

MODEL_NAME = "llama3.2:latest"

MAX_TOKENS = 2048

TEMPERATURE = 0

# Recovery strategy parameters
VERIFICATION_THRESHOLD = 0.80  # τ: confidence threshold for claim acceptance
MAX_REGENERATIONS = 3          # A2: max full plan regenerations
MAX_REPAIR_ATTEMPTS = 1        # A3: repairs per claim (1 = no loop)

# Adaptive recovery (A4) parameters
ADAPTATION_MODE = "greedy"     # "greedy", "confidence_based", "dependency_based"

