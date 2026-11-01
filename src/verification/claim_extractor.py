"""
Decompose Agent A's reasoning into atomic claims with dependencies.

    [{"claim_id": "c1", "text": "...", "depends_on": []}, ...]
"""

from src.llm_client import call_llm, parse_json


CLAIMS_SCHEMA = {
    "type": "object",
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim_id": {"type": "string"},
                    "text": {"type": "string"},
                    "depends_on": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["claim_id", "text", "depends_on"],
            },
        }
    },
    "required": ["claims"],
}


PROMPT = """You are an atomic claim extraction module for a multi-agent
mathematical reasoning system.

Decompose the reasoning below into the smallest meaningful factual or
mathematical claims, in the order they appear.

Rules:
- Each claim must be independently checkable and must keep the numbers and
  calculations exactly as written (e.g. "Total stamps = 3 x 15 = 45").
- Do NOT fix, rewrite or solve anything. Do NOT add claims that are not in the
  reasoning.
- "depends_on" lists the IDs of EARLIER claims whose values this claim uses.
- Use IDs c1, c2, c3, ...

Example
Reasoning:
John has 12 apples. He gives away 5 apples. So he has 12 - 5 = 7 apples left.
Output:
{{"claims": [
  {{"claim_id": "c1", "text": "John has 12 apples.", "depends_on": []}},
  {{"claim_id": "c2", "text": "John gives away 5 apples.", "depends_on": []}},
  {{"claim_id": "c3", "text": "John has 12 - 5 = 7 apples left.", "depends_on": ["c1", "c2"]}}
]}}

Original problem:
{problem}

Agent A reasoning:
{reasoning}

Return only the JSON object."""


def normalize_claims(raw_claims):
    """Make IDs unique (c1..cn) and keep only dependencies on earlier claims."""
    out = []
    id_map = {}
    for index, claim in enumerate(raw_claims or []):
        if not isinstance(claim, dict):
            continue
        text = str(claim.get("text", "")).strip()
        if not text:
            continue
        new_id = f"c{len(out) + 1}"
        old_id = str(claim.get("claim_id", f"c{index + 1}"))
        deps = claim.get("depends_on") or []
        if not isinstance(deps, list):
            deps = []
        mapped = []
        for d in deps:
            d = id_map.get(str(d))
            if d and d not in mapped:
                mapped.append(d)   # earlier claims only -> graph stays acyclic
        id_map.setdefault(old_id, new_id)
        out.append({"claim_id": new_id, "text": text, "depends_on": mapped})
    return out


def extract_claims(problem, reasoning):
    raw, _, _ = call_llm(
        system_prompt="You are a precise atomic claim extraction module.",
        user_content=PROMPT.format(problem=problem, reasoning=reasoning),
        schema=CLAIMS_SCHEMA,
    )
    data = parse_json(raw)
    if isinstance(data, dict):
        data = data.get("claims", [])
    if not isinstance(data, list):
        raise ValueError("Claim extractor did not return a list of claims.")
    return normalize_claims(data)


def claims_to_plan(claims):
    """Rebuild a plan text from claims (used after claims are repaired)."""
    return "\n".join(
        f"Step {i + 1}: {c['text']}" for i, c in enumerate(claims) if c.get("text")
    )
