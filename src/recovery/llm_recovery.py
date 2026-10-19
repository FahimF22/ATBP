from src.llm_client import call_llm


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

    text, _, _ = call_llm(
        system_prompt="You are Agent A, a mathematical planning and reasoning agent.",
        user_content=prompt,
    )
    return text


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

Fix ONLY the specific issue in the verification feedback below. Preserve all numbers and values exactly.

CRITICAL RULES — VIOLATION CAUSES WRONG ANSWERS:
- Do NOT change any number, quantity, price, or value from the original claim unless it is provably mathematically wrong given the original problem statement.
- Do NOT introduce any new facts, prices, rates, or quantities that are not in the original problem.
- Do NOT add new information beyond what the original problem provides.
- ONLY fix: grammar errors, unclear phrasing, or logical flow issues.
- ONLY address the specific verification feedback provided — nothing else.
- If you cannot fix the claim without changing numbers, return the original claim UNCHANGED.
- The fixed claim must contain the same numerical values as the original claim.

Do not rewrite other claims.
Do not add explanations.
Do not solve the entire problem.

Return only the corrected atomic claim.
"""

    text, _, _ = call_llm(
        system_prompt="You repair individual mathematical reasoning claims.",
        user_content=prompt,
    )
    return text.strip()