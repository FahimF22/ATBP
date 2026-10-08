import json
import re

from openai import OpenAI

from config.config import MODEL_NAME, MAX_TOKENS


client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama"
)


def _extract_json(text):
    """
    Extract a JSON array from an LLM response.

    Handles responses where the model surrounds JSON
    with markdown code fences or additional text.
    """

    text = text.strip()

    # Remove markdown code fences.
    text = re.sub(
        r"^```(?:json)?\s*",
        "",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r"\s*```$",
        "",
        text
    )

    # Try direct JSON parsing first.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Search for a JSON array.
    match = re.search(
        r"\[[\s\S]*\]",
        text
    )

    if not match:
        raise ValueError(
            "Could not find a JSON array in "
            "claim extractor response."
        )

    return json.loads(match.group(0))


def extract_claims(problem, reasoning):
    """
    Decompose Agent A's reasoning into atomic claims.

    Returns:

    [
        {
            "claim_id": "c1",
            "text": "...",
            "depends_on": ["c0"]
        }
    ]
    """

    prompt = f"""
You are an atomic claim extraction module for a
multi-agent mathematical reasoning system.

Your job is to decompose the reasoning into the smallest
meaningful factual or mathematical claims.

A claim should be independently verifiable.

Do NOT rewrite the reasoning.
Do NOT solve the problem yourself.
Do NOT add claims that are not present in the reasoning.

For every claim provide:

1. claim_id
2. text
3. depends_on

"depends_on" must contain the IDs of claims that this
claim logically relies upon.

Example:

Reasoning:
John has 12 apples.
He gives away 5 apples.
Therefore he has 7 apples remaining.

Output:
[
  {{
    "claim_id": "c1",
    "text": "John has 12 apples.",
    "depends_on": []
  }},
  {{
    "claim_id": "c2",
    "text": "John gives away 5 apples.",
    "depends_on": []
  }},
  {{
    "claim_id": "c3",
    "text": "John has 7 apples remaining.",
    "depends_on": ["c1", "c2"]
  }}
]

Original problem:
{problem}

Agent A reasoning:
{reasoning}

Return ONLY valid JSON.
"""

    response = client.chat.completions.create(
        model=MODEL_NAME,
        temperature=0,
        max_tokens=MAX_TOKENS,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a precise atomic claim "
                    "extraction module."
                )
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    raw = response.choices[0].message.content

    claims = _extract_json(raw)

    if not isinstance(claims, list):
        raise ValueError(
            "Claim extractor must return a JSON list."
        )

    normalized = []

    for index, claim in enumerate(claims):

        claim_id = claim.get(
            "claim_id",
            f"c{index + 1}"
        )

        text = claim.get(
            "text",
            ""
        ).strip()

        depends_on = claim.get(
            "depends_on",
            []
        )

        if not text:
            continue

        if not isinstance(
            depends_on,
            list
        ):
            depends_on = []

        normalized.append(
            {
                "claim_id": claim_id,
                "text": text,
                "depends_on": depends_on
            }
        )

    return normalized