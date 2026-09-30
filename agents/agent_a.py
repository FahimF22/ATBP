from openai import OpenAI
from config.config import MODEL_NAME, MAX_TOKENS, TEMPERATURE


client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama"
)


def agent_a(problem):
    prompt = f"""
You are Agent A in a sequential multi-agent reasoning system.

Your role is Planner/Reasoner.

Analyze the following mathematical word problem and produce
a clear intermediate reasoning plan for Agent B.

Do not give unnecessary discussion.
Identify the important quantities, operations, and reasoning steps.

Problem:
{problem}
"""

    response = client.chat.completions.create(
        model=MODEL_NAME,
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
        messages=[
            {
                "role": "system",
                "content": "You are Agent A, the planning and reasoning agent."
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    return response.choices[0].message.content