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
You are a claim verification module for a mathematical reasoning system.

Your task: Determine whether the given atomic claim is valid based on the original problem and context.

Original problem:
{problem}

Context:
{evidence}

Atomic claim:
{claim["text"]}

Apply these rules in order:

1. DIRECT QUOTE RULE: If the claim text directly quotes or closely paraphrases a fact explicitly stated in the original problem, it is VALID with confidence 0.95. Do NOT second-guess it.

2. LOGICAL SUPPORT RULE: If the claim is implicitly but logically supported by the problem (a necessary intermediate step), it is VALID with confidence 0.80.

3. CONTRADICTION RULE: Only mark a claim INVALID if it DIRECTLY CONTRADICTS a number, quantity, or fact stated in the problem. Confidence 0.90 for a true contradiction.

4. UNSUPPORTED ≠ INVALID: Claims that introduce intermediate reasoning steps not verbatim in the problem are NOT automatically invalid. Mathematical reasoning requires intermediate steps.

5. NEVER mark a claim invalid merely because it lacks numerical detail or because the problem does not explicitly enumerate every sub-quantity.

Return ONLY this JSON format:

{{
  "is_valid": true,
  "confidence": 0.95,
  "rationale": "Rule X applied: explanation citing the specific rule used."
}}

Verification threshold: {tau}
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