from openai import OpenAI

from config.config import (
    MODEL_NAME,
    MAX_TOKENS,
)


client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama"
)


def regenerate_plan(problem):
    """
    A2:
    Completely regenerate Agent A's plan.
    """

    prompt = f"""
You are Agent A in a sequential mathematical
reasoning system.

Generate a completely new reasoning plan for
the following problem.

Reconsider the problem from the beginning.
Do not rely on any previous reasoning.

Problem:
{problem}

Return only the reasoning plan.
"""

    response = client.chat.completions.create(
        model=MODEL_NAME,
        temperature=0,
        max_tokens=MAX_TOKENS,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are Agent A, a mathematical "
                    "planning and reasoning agent."
                )
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    return response.choices[0].message.content


def repair_claim(
    problem,
    claim,
    rationale=""
):
    """
    A3:
    Repair ONLY the faulty atomic claim.
    """

    prompt = f"""
You are repairing one faulty atomic claim inside
a mathematical reasoning chain.

Original problem:
{problem}

Faulty claim:
{claim["text"]}

Verification feedback:
{rationale}

Produce a corrected version of ONLY this claim.

Do not rewrite other claims.
Do not add explanations.
Do not solve the entire problem.

Return only the corrected atomic claim.
"""

    response = client.chat.completions.create(
        model=MODEL_NAME,
        temperature=0,
        max_tokens=MAX_TOKENS,
        messages=[
            {
                "role": "system",
                "content": (
                    "You repair individual mathematical "
                    "reasoning claims."
                )
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    return response.choices[0].message.content.strip()