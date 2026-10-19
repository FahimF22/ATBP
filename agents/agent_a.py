from openai import OpenAI
from config.config import MODEL_NAME, MAX_TOKENS, TEMPERATURE


client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama",
    timeout=180.0
)


def agent_a(problem):
    prompt = f"""
Output ONLY the step-by-step reasoning plan. Do NOT include any preamble, greeting, or meta-commentary. Start immediately with Step 1.

You are Agent A in a sequential multi-agent reasoning system.

Your role is Planner/Reasoner.

Analyze the following mathematical word problem and produce
a clear intermediate reasoning plan for Agent B.

Do not give unnecessary discussion.
Identify the important quantities, operations, and reasoning steps.

For problems with nested multiplications or repeated operations,
enforce explicit step-by-step listing of each factor before combining them.

Example — "3 sprints 3 times a week, 60 meters each":
  Step 1: Sprint frequency = 3 times per week
  Step 2: Sprints per session = 3
  Step 3: Total sprints per week = 3 x 3 = 9
  Step 4: Distance per sprint = 60 meters
  Step 5: Total distance = 9 x 60 = 540 meters

Always list all multipliers explicitly before combining them.

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