"""
LLM-based recovery primitives.

repair_claim   - fix one faulty claim using the verifier's feedback
rederive_claim - recompute a dependent claim after its prerequisites changed
regenerate_plan - kept for older scripts (use agents.agent_a with feedback now)
"""

from src.llm_client import call_llm


def repair_claim(problem, claim, rationale="", earlier_claims=None):
    """Return corrected text for one faulty claim."""
    earlier = "\n".join(f"- {c['text']}" for c in (earlier_claims or [])) or "(none)"
    prompt = f"""You are repairing one faulty step inside a solution to a math word problem.

Problem:
{problem}

Earlier steps (treat as correct):
{earlier}

Faulty step:
{claim["text"]}

Why it is wrong:
{rationale or "The verifier rejected this step."}

Rewrite ONLY this step so that it is correct. Fix the wrong value or
operation, keep the same wording and every other number, and do not add new
facts or later steps.

Return only the corrected step, as one sentence."""
    text, _, _ = call_llm(
        system_prompt="You repair individual mathematical reasoning steps.",
        user_content=prompt,
    )
    return _first_line(text) or claim["text"]


def rederive_claim(problem, claim, prerequisites):
    """Rewrite a claim so it is consistent with (corrected) prerequisite claims."""
    prereq = "\n".join(f"- {c['text']}" for c in prerequisites) or "(none)"
    prompt = f"""A step in a math solution may use values that were just corrected.

Problem:
{problem}

Corrected earlier steps:
{prereq}

Step to update:
{claim["text"]}

Rewrite the step so that it uses the corrected values above and recompute any
numbers that depend on them. Keep the same wording otherwise. If nothing needs
to change, return the step unchanged.

Return only the updated step, as one sentence."""
    text, _, _ = call_llm(
        system_prompt="You keep mathematical reasoning steps consistent.",
        user_content=prompt,
    )
    return _first_line(text) or claim["text"]


def regenerate_plan(problem, feedback=None, temperature=0.7, seed=None):
    from agents.agent_a import agent_a

    return agent_a(problem, feedback=feedback, temperature=temperature, seed=seed)


def _first_line(text):
    text = (text or "").strip().strip('"').strip()
    for prefix in ("Corrected step:", "Updated step:", "Step:"):
        if text.lower().startswith(prefix.lower()):
            text = text[len(prefix):].strip()
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    return lines[0] if lines else ""
