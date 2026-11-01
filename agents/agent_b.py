from config import config as cfg
from src.llm_client import call_llm


LEAN_PROMPT = """
You are Agent B in a sequential multi-agent reasoning system.

Your role is Intermediate Solver.

Check Agent A's reasoning for the problem below: verify every calculation and
whether the right quantities and operations are used.

Be brief:
- If every step is correct, write "All steps correct." and the final value.
- If a step is wrong, write only the corrected steps (one line each, with the
  calculation) and the corrected final value.
Do not restate correct steps or explain them.

Original problem:
{problem}

Agent A reasoning:
{agent_a_output}
"""


def agent_b(problem, agent_a_output):
    if cfg.LEAN:
        prompt = LEAN_PROMPT.format(problem=problem, agent_a_output=agent_a_output)
    else:
        prompt = _full_prompt(problem, agent_a_output)
    try:
        text, _, _ = call_llm(
            system_prompt="You are Agent B, the intermediate solver.",
            user_content=prompt,
        )
        return text
    except Exception as e:
        return f"[Error in Agent B: {str(e)[:200]}]"


def _full_prompt(problem, agent_a_output):
    return f"""
You are Agent B in a sequential multi-agent reasoning system.

Your role is Intermediate Solver.

You receive:
1. The original problem.
2. The reasoning produced by Agent A.

Check Agent A's work for errors. If you find mistakes in calculation
or logic, recompute correctly. Show your work step-by-step.

Verify every arithmetic operation you perform. Double-check multiplications and additions. If you find an error in Agent A, state it clearly and provide the correct computation.

Use Agent A's reasoning as a starting point, verify every calculation,
continue the reasoning, and produce a solution that Agent C can use.

Original problem:
{problem}

Agent A reasoning:
{agent_a_output}

Provide the intermediate solution clearly.
"""
