from openai import OpenAI
from config.config import MODEL_NAME, MAX_TOKENS, TEMPERATURE


client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama"
)


def agent_b(problem, agent_a_output):
    prompt = f"""
You are Agent B in a sequential multi-agent reasoning system.

Your role is Intermediate Solver.

You receive:
1. The original problem.
2. The reasoning produced by Agent A.

Use Agent A's reasoning as an input, check the calculations,
continue the reasoning, and produce a solution that Agent C
can use.

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