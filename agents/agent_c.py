from openai import OpenAI
from config.config import API_KEY, MODEL_NAME, MAX_TOKENS, TEMPERATURE


client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama",
    timeout=180.0
)


def agent_c(problem, agent_a_output, agent_b_output):
    prompt = f"""
You are Agent C in a sequential multi-agent reasoning system.

Your role is Final Answer Generator.

Using the original problem and the intermediate reasoning
from Agents A and B, produce the final answer.

You MUST respond with EXACTLY this structure and nothing else:
**Reasoning Summary:** [1-2 sentences explaining the solution]
**Answer:** [ONLY the final numerical value — a single integer or decimal, no units, no words, no punctuation]

STOP immediately after the **Answer:** line. Do NOT write anything after the answer number. Any text after **Answer:** will be ignored and may cause scoring errors.

Do NOT include any calculations, alternatives, or additional text after the **Answer:** line.
Do NOT mention the multi-agent system.

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