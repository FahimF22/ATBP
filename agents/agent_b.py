from openai import OpenAI
from config.config import MODEL_NAME, MAX_TOKENS, TEMPERATURE


client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama",
    timeout=180.0
)


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

    response = client.chat.completions.create(
        model=MODEL_NAME,
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
        messages=[
            {
                "role": "system",
                "content": "You are Agent B, the intermediate solver."
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    return response.choices[0].message.content