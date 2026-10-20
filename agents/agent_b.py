from src.llm_client import call_llm


def agent_b(problem, agent_a_output):
    prompt = f"""
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

    try:
        text, _, _ = call_llm(
            system_prompt="You are Agent B, the intermediate solver.",
            user_content=prompt,
        )
        return text
    except Exception as e:
        return f"[Error in Agent B: {str(e)[:200]}]"
