"""
Independent check of a plan's final answer (part of ATBP_V2).

The model writes a short Python program that solves the problem on its own.
The program runs in a separate, isolated Python process with a time limit,
and its answer is compared with the value the plan concludes with:

    agree     -> flags raised only by the LLM judge are overruled
    disagree  -> the LLM names the first wrong step, which is flagged with
                 the program's answer as evidence for the repair

A program that fails, times out or uses anything outside plain arithmetic
gives no signal, and verification is left unchanged.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from functools import lru_cache

from src.llm_client import call_llm, parse_json
from src.verification.arithmetic_checker import normalize, numbers_in


CODE_SCHEMA = {
    "type": "object",
    "properties": {"code": {"type": "string"}},
    "required": ["code"],
}

LOCATE_SCHEMA = {
    "type": "object",
    "properties": {
        "claim_id": {"type": "string"},
        "rationale": {"type": "string"},
    },
    "required": ["claim_id", "rationale"],
}

CODE_PROMPT = """Solve this math word problem by writing a short Python program.

Rules:
- Read the problem carefully and compute the exact quantity the question asks for.
- Use plain Python arithmetic (the math module is allowed). No input(), files or printing.
- Store the final numeric answer in a variable named `answer`.

Problem:
{problem}

Return a JSON object with the program in the "code" field."""

LOCATE_PROMPT = """A step-by-step plan for a math word problem concludes {plan_value},
but an independent calculation gives {program_value}.

Problem:
{problem}

Plan steps:
{listing}

Find the FIRST step that is wrong (wrong quantity, wrong operation, misread
question or wrong arithmetic). If you are convinced the plan is right and the
independent calculation is wrong, answer with claim_id "none".
Give the claim id and a one-sentence rationale that says what the step should be."""

_ALLOWED_IMPORTS = {"math", "fractions", "decimal"}
_BANNED_NAMES = {
    "open", "exec", "eval", "compile", "__import__", "input", "globals", "locals",
    "getattr", "setattr", "delattr", "vars", "breakpoint", "exit", "quit", "help",
    "memoryview", "classmethod", "staticmethod", "super", "type",
}

_RUNNER = """
import sys
src = sys.stdin.read()
scope = {}
exec(compile(src, "<program>", "exec"), scope)
print(repr(float(scope["answer"])))
"""


def _is_safe(code: str) -> bool:
    """Allow only plain arithmetic code: no dangerous names, imports or dunders."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(a.name.split(".")[0] not in _ALLOWED_IMPORTS for a in node.names):
                return False
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] not in _ALLOWED_IMPORTS:
                return False
        elif isinstance(node, ast.Name) and node.id in _BANNED_NAMES:
            return False
        elif isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            return False
        elif isinstance(node, (ast.Global, ast.Nonlocal, ast.AsyncFunctionDef,
                               ast.Await)):
            return False
    return True


def run_program(code: str, timeout: float = 10.0) -> float | None:
    """Run model-written code in an isolated Python process; return `answer`."""
    if not _is_safe(code):
        return None
    try:
        proc = subprocess.run(
            [sys.executable, "-I", "-S", "-c", _RUNNER],
            input=code, capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return None
    if proc.returncode != 0:
        return None
    try:
        return float(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return None


@lru_cache(maxsize=4096)
def program_answer(problem: str) -> float | None:
    """The independent answer for a problem (one cached LLM call)."""
    try:
        raw, _, _ = call_llm(
            system_prompt="You are a careful programmer who solves math word problems.",
            user_content=CODE_PROMPT.format(problem=problem),
            schema=CODE_SCHEMA,
        )
        code = (parse_json(raw) or {}).get("code", "")
    except Exception:
        return None
    return run_program(code) if code else None


def _value(text: str) -> float | None:
    """The value a claim concludes with: first number after the last '='."""
    norm = normalize(text)
    if "=" not in norm:
        return None
    m = re.search(r"-?\$?\d[\d,]*(?:\.\d+)?", norm.rsplit("=", 1)[1])
    if not m:
        return None
    try:
        return float(m.group(0).replace("$", "").replace(",", ""))
    except ValueError:
        return None


def plan_answer(claims) -> float | None:
    """The value the plan's final step concludes with, or None when the final
    step states no single value (e.g. "Combine the totals to find the salary").
    Earlier steps are not used: their values are usually intermediate results."""
    claims = list(claims)
    if not claims:
        return None
    last = claims[-1]["text"]
    v = _value(last)
    if v is not None:
        return v
    nums = sorted(numbers_in(last))
    return nums[0] if len(nums) == 1 else None


def same_value(a: float, b: float) -> bool:
    return abs(a - b) <= 1e-6 * max(1.0, abs(a), abs(b)) or round(a, 2) == round(b, 2)


def agrees(claims, value: float) -> bool:
    """True if the plan's final step reaches `value`."""
    final = plan_answer(claims)
    if final is not None and same_value(final, value):
        return True
    return bool(claims) and any(same_value(n, value) for n in numbers_in(claims[-1]["text"]))


def locate_error(problem, claims, plan_value, program_value):
    """Ask which step is the first wrong one. Returns (claim_id or None, rationale)."""
    listing = "\n".join(f"{c['claim_id']}: {c['text']}" for c in claims)
    try:
        raw, _, _ = call_llm(
            system_prompt="You are a careful mathematical claim verifier.",
            user_content=LOCATE_PROMPT.format(
                problem=problem, listing=listing,
                plan_value=_fmt(plan_value), program_value=_fmt(program_value)),
            schema=LOCATE_SCHEMA,
        )
        data = parse_json(raw) or {}
    except Exception:
        return None, ""
    cid = str(data.get("claim_id", "")).strip()
    ids = {c["claim_id"] for c in claims}
    return (cid if cid in ids else None), str(data.get("rationale", ""))


def _fmt(x):
    if x is None:
        return "no clear value"
    return str(int(x)) if float(x).is_integer() else f"{x:g}"
