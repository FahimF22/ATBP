import os

from dotenv import load_dotenv

load_dotenv()

# Ollama runs locally, so no OpenAI API key is required.
API_KEY = "ollama"

MODEL_NAME = "llama3.2:latest"

MAX_TOKENS = 2048

TEMPERATURE = 0

