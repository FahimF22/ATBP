"""
ATBP configuration.

Everything runs on free, local models through Ollama by default.
Any value can be overridden with an environment variable (or a .env file),
e.g.  ATBP_MODEL=llama3.1:8b python experiments/run_natural.py ...
"""

import os

from dotenv import load_dotenv

load_dotenv()


def _env(name, default, cast=str):
    value = os.getenv(name)
    if value is None or value == "":
        return default
    if cast is bool:
        return value.strip().lower() in ("1", "true", "yes", "on")
    return cast(value)


# ---------------------------------------------------------------------------
# Backend
#   "ollama"  : local Ollama (free, default)
#   "openai_compatible" : any OpenAI-style endpoint (e.g. a free-tier host);
#                         set ATBP_BASE_URL and ATBP_API_KEY
#   "gemini" / "openai" : kept for old runs; these are paid/limited APIs
# ---------------------------------------------------------------------------
LLM_BACKEND = _env("ATBP_BACKEND", "ollama")

OLLAMA_URL = _env("ATBP_OLLAMA_URL", "http://localhost:11434")
MODEL_NAME = _env("ATBP_MODEL", "qwen2.5:7b")

# Context window sent to Ollama on every call. Keep it constant: changing it
# forces Ollama to reload the model.
NUM_CTX = _env("ATBP_NUM_CTX", 4096, int)
KEEP_ALIVE = _env("ATBP_KEEP_ALIVE", "30m")

# OpenAI-compatible endpoint (only used when LLM_BACKEND="openai_compatible")
BASE_URL = _env("ATBP_BASE_URL", "")
API_KEY = _env("ATBP_API_KEY", "")

# Paid backends (not used by default). For gpt-4o-mini set ATBP_BACKEND=openai
# and OPENAI_API_KEY in .env.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL_NAME = "gemini-flash-latest"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL_NAME = _env("ATBP_OPENAI_MODEL", "gpt-4o-mini")

MAX_TOKENS = _env("ATBP_MAX_TOKENS", 2048, int)

# Token-saving variant (off by default). When on: Agent B writes a short
# check instead of a full step-by-step re-solution, and the verifier keeps its
# rationales short. Results go to a separate "<model>_lean" folder.
LEAN = _env("ATBP_LEAN", False, bool)

# Improved verification and recovery (off by default; ATBP_V2=1 turns all on).
# Results go to a separate "<model>_v2" folder.
#   VALUE_CHECK   the LLM judge must name the value a wrong step should have;
#                 a flag whose "correct" value equals the stated one is dropped
#   PROGRAM_CHECK an independent Python solution checks the plan's answer:
#                 agreement overrules LLM-only flags, disagreement flags the
#                 first wrong step with the program's answer as evidence
#   NO_HARM       if the recovered plan still fails verification, keep the
#                 original plan
V2 = _env("ATBP_V2", False, bool)
VALUE_CHECK = _env("ATBP_VALUE_CHECK", V2, bool)
PROGRAM_CHECK = _env("ATBP_PROGRAM_CHECK", V2, bool)
NO_HARM = _env("ATBP_NO_HARM", V2, bool)

# Problems processed at the same time by the experiment scripts (--workers).
# API backends mostly wait on the network, so several at once is much faster.
# A local Ollama GPU runs one request at a time, so 1 is best there.
WORKERS = _env("ATBP_WORKERS", 1 if LLM_BACKEND == "ollama" else 8, int)
TEMPERATURE = 0.0              # first-pass generation is greedy
REGEN_TEMPERATURE = 0.7        # regeneration samples a new plan
BASE_SEED = _env("ATBP_SEED", 1234, int)

# Disk cache of LLM calls. Makes runs resumable, makes all systems share the
# same initial Agent A plan, and keeps the original token/latency cost so cost
# comparisons stay fair even when a call is served from cache.
USE_CACHE = _env("ATBP_CACHE", True, bool)
CACHE_PATH = _env("ATBP_CACHE_PATH", "cache/llm_cache.sqlite")

# ---------------------------------------------------------------------------
# Verification
#   "llm"        : LLM judge only (the original design)
#   "arithmetic" : deterministic checks only
#   "hybrid"     : deterministic arithmetic/grounding checks, then LLM judge
# ---------------------------------------------------------------------------
VERIFIER_MODE = _env("ATBP_VERIFIER", "hybrid")
VERIFICATION_THRESHOLD = _env("ATBP_TAU", 0.80, float)   # tau
GROUNDING_CHECK = _env("ATBP_GROUNDING", True, bool)
BATCH_VERIFY = _env("ATBP_BATCH_VERIFY", True, bool)

# ---------------------------------------------------------------------------
# Recovery
# ---------------------------------------------------------------------------
MAX_REGENERATIONS = _env("ATBP_MAX_REGEN", 3, int)

# A4 policy: if recomputing a branch would touch at least this share of all
# claims, regenerating the agent is about as costly, so prefer that.
BRANCH_COST_RATIO = _env("ATBP_BRANCH_COST_RATIO", 0.6, float)
# Share of failed claims at which the plan is treated as broken overall.
FULL_REGEN_FAILURE_RATE = _env("ATBP_FULL_REGEN_RATE", 0.5, float)
