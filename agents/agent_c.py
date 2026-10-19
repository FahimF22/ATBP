from openai import OpenAI
from config.config import API_KEY, MODEL_NAME, MAX_TOKENS, TEMPERATURE


client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama"
)


def agent_c(problem, agent_a_output, agent_b_output):
    prompt = f"""
You are Agent C in a sequential multi-agent reasoning system.

Your role is Final Answer Generator.

Using the original problem and the intermediate reasoning
from Agents A and B, produce the final answer.

Give:
1. A concise explanation.
2. The final numerical answer.

Do not mention the multi-agent system.

IMPORTANT: Your final line MUST be exactly:
**Answer:** [the single final numerical value, digits only, no units or explanation]

Do not write anything after the Answer line.

Original problem:
{problem}

Agent A:
{agent_a_output}

Agent B:
{agent_b_output}
"""

    response = client.chat.completions.create(
        model=MODEL_NAME,
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
        messages=[
            {
                "role": "system",
                "content": "You are Agent C, the final answer generator."
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    return response.choices[0].message.content