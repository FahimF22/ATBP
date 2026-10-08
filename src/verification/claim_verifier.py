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
    Extract a JSON object from an LLM response.
    """

    text = text.strip()

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

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(
        r"\{[\s\S]*\}",
        text
    )

    if not match:
        raise ValueError(
            "Could not find JSON object in "
            "claim verifier response."
        )

    return json.loads(match.group(0))


def verify_claim(
    problem,
    claim,
    context="",
    tau=0.80
):
    """
    Verify one atomic claim.

    Returns:

    {
        "claim_id": "...",
        "is_valid": true/false,
        "confidence": 0.0-1.0,
        "rationale": "..."
    }
    """

    if context:
        evidence = context
    else:
        evidence = problem

    prompt = f"""
You are a strict claim verification module for a
mathematical reasoning system.

Determine whether the given atomic claim is supported
by the original problem and the supplied context.

Do not assume that the claim is correct merely because
it appears in the reasoning.

Check:
- numerical values
- arithmetic
- relationships
- quantities
- logical conclusions
- whether the claim is actually supported

Original problem:
{problem}

Context:
{evidence}

Atomic claim:
{claim["text"]}

Return ONLY this JSON format:

{{
  "is_valid": true,
  "confidence": 0.95,
  "rationale": "The claim is directly supported by the problem."
}}

Rules:

is_valid:
- true if the claim is supported/correct
- false if the claim is contradicted, unsupported,
  or mathematically incorrect

confidence:
- number between 0.0 and 1.0

Use confidence to represent how certain you are.

Verification threshold:
{tau}
"""

    response = client.chat.completions.create(
        model=MODEL_NAME,
        temperature=0,
        max_tokens=MAX_TOKENS,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a strict mathematical "
                    "claim verifier."
                )
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    raw = response.choices[0].message.content

    result = _extract_json(raw)

    is_valid = bool(
        result.get("is_valid", False)
    )

    try:
        confidence = float(
            result.get("confidence", 0.0)
        )
    except (
        TypeError,
        ValueError
    ):
        confidence = 0.0

    confidence = max(
        0.0,
        min(1.0, confidence)
    )

    # A claim below tau is treated as failed.
    accepted = (
        is_valid
        and confidence >= tau
    )

    return {
        "claim_id": claim["claim_id"],
        "is_valid": accepted,
        "confidence": confidence,
        "rationale": result.get(
            "rationale",
            ""
        )
    }


def verify_claims(
    problem,
    claims,
    context="",
    tau=0.80
):
    """
    Verify a complete list of atomic claims.
    """

    results = []

    for claim in claims:

        result = verify_claim(
            problem=problem,
            claim=claim,
            context=context,
            tau=tau
        )

        results.append(
            {
                **claim,
                **result
            }
        )

    return results