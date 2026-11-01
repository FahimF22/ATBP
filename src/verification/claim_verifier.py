"""
Claim verification.

verify_claims(problem, claims, context, tau, mode) returns one record per claim:

    {**claim, "is_valid": bool, "confidence": float, "rationale": str,
     "source": "arithmetic" | "grounding" | "llm" | "llm_error",
     "correct_value": float | None,   # set when arithmetic fixed a result
     "stated_value": float | None}

Modes (cfg.VERIFIER_MODE):
    "llm"        LLM judge only (original design)
    "arithmetic" deterministic checks only
    "hybrid"     deterministic checks first, LLM judge for everything else
"""

from config import config as cfg
from src.llm_client import call_llm, parse_json
from src.verification.arithmetic_checker import (
    check_arithmetic,
    problem_numbers,
    numbers_in,
    ungrounded_operands,
    fmt_number,
)


VERDICTS_SCHEMA = {
    "type": "object",
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim_id": {"type": "string"},
                    "is_valid": {"type": "boolean"},
                    "confidence": {"type": "number"},
                    "rationale": {"type": "string"},
                },
                "required": ["claim_id", "is_valid", "confidence", "rationale"],
            },
        }
    },
    "required": ["verdicts"],
}

SINGLE_SCHEMA = {
    "type": "object",
    "properties": {
        "is_valid": {"type": "boolean"},
        "confidence": {"type": "number"},
        "rationale": {"type": "string"},
    },
    "required": ["is_valid", "confidence", "rationale"],
}

RULES = """Rules:
1. A claim that restates a fact from the problem correctly is VALID (confidence 0.95).
2. A necessary intermediate step that follows logically from the problem and
   from earlier claims is VALID (confidence 0.85).
3. A claim is INVALID if it uses a wrong quantity from the problem, applies the
   wrong operation, misreads the question, or uses a value that contradicts an
   earlier claim (confidence 0.9).
4. Intermediate steps that are not written verbatim in the problem are NOT
   invalid for that reason alone.
{arith_rule}"""

ARITH_RULE_LLM = "5. Recompute every calculation. A wrong result makes the claim INVALID."
ARITH_RULE_HYBRID = ("5. The arithmetic has already been checked by a calculator. Focus on "
                     "whether the right quantities and operations are used.")


LEAN_NOTE = "\nKeep each rationale under 15 words."


# VALUE_CHECK variants: the judge also gives the value a wrong claim should have.
_VALUE = {"type": ["number", "null"]}
VERDICTS_SCHEMA_V2 = {
    "type": "object",
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim_id": {"type": "string"},
                    "is_valid": {"type": "boolean"},
                    "confidence": {"type": "number"},
                    "rationale": {"type": "string"},
                    "correct_value": _VALUE,
                },
                "required": ["claim_id", "is_valid", "confidence", "rationale", "correct_value"],
            },
        }
    },
    "required": ["verdicts"],
}
SINGLE_SCHEMA_V2 = {
    "type": "object",
    "properties": {
        "is_valid": {"type": "boolean"},
        "confidence": {"type": "number"},
        "rationale": {"type": "string"},
        "correct_value": _VALUE,
    },
    "required": ["is_valid", "confidence", "rationale", "correct_value"],
}
VALUE_NOTE = ("\nFor an INVALID claim, set correct_value to the number the claim should "
              "conclude with (null if it has no single numeric result). For a VALID "
              "claim, set correct_value to null.")


def _arith_rule(mode):
    return ARITH_RULE_HYBRID if mode == "hybrid" else ARITH_RULE_LLM


# ---------------------------------------------------------------------------
# Deterministic checks
# ---------------------------------------------------------------------------

def _deterministic(problem, claims):
    """Return {claim_id: verdict} for claims with a deterministic finding."""
    findings = {}
    known = problem_numbers(problem)
    for claim in claims:
        text = claim["text"]
        report = check_arithmetic(text)
        if report.issues:
            issue = report.issues[0]
            findings[claim["claim_id"]] = {
                "is_valid": False,
                "confidence": 1.0,
                "rationale": issue.message(),
                "source": "arithmetic",
                "correct_value": issue.correct,
                "stated_value": issue.stated,
            }
        elif cfg.GROUNDING_CHECK:
            local = set(known)
            # numbers produced inside this claim (after "=") are not inputs
            if "=" in text:
                local |= numbers_in(text.split("=", 1)[1])
            bad = ungrounded_operands(text, local)
            if bad:
                shown = ", ".join(fmt_number(b) for b in bad)
                findings[claim["claim_id"]] = {
                    "is_valid": False,
                    "confidence": 0.85,
                    "rationale": (f"The value(s) {shown} used in this calculation do not "
                                  f"appear in the problem or in earlier steps."),
                    "source": "grounding",
                    "correct_value": None,
                    "stated_value": bad[0],
                }
        # every number in this claim becomes known for later claims
        known |= numbers_in(text)
        known |= {round(1 - n, 6) for n in numbers_in(text) if 0 < n < 1}
    return findings


# ---------------------------------------------------------------------------
# LLM judge
# ---------------------------------------------------------------------------

def _llm_batch(problem, claims, mode):
    listing = "\n".join(f"{c['claim_id']}: {c['text']}" for c in claims)
    prompt = f"""You are verifying the steps of a solution to a math word problem.

Problem:
{problem}

Claims (in order; later claims may use earlier ones):
{listing}

{RULES.format(arith_rule=_arith_rule(mode))}

Return one verdict for EVERY claim id, with a short rationale."""
    if cfg.LEAN:
        prompt += LEAN_NOTE
    if cfg.VALUE_CHECK:
        prompt += VALUE_NOTE
    raw, _, _ = call_llm(
        system_prompt="You are a careful mathematical claim verifier.",
        user_content=prompt,
        schema=VERDICTS_SCHEMA_V2 if cfg.VALUE_CHECK else VERDICTS_SCHEMA,
    )
    data = parse_json(raw)
    verdicts = data.get("verdicts", []) if isinstance(data, dict) else data
    out = {}
    for v in verdicts or []:
        if isinstance(v, dict) and v.get("claim_id"):
            out[str(v["claim_id"])] = v
    return out


def _llm_single(problem, claim, earlier, mode):
    context = "\n".join(f"{c['claim_id']}: {c['text']}" for c in earlier) or "(none)"
    prompt = f"""You are verifying one step of a solution to a math word problem.

Problem:
{problem}

Earlier claims:
{context}

Claim to verify:
{claim['text']}

{RULES.format(arith_rule=_arith_rule(mode))}"""
    if cfg.LEAN:
        prompt += LEAN_NOTE
    if cfg.VALUE_CHECK:
        prompt += VALUE_NOTE
    raw, _, _ = call_llm(
        system_prompt="You are a careful mathematical claim verifier.",
        user_content=prompt,
        schema=SINGLE_SCHEMA_V2 if cfg.VALUE_CHECK else SINGLE_SCHEMA,
    )
    return parse_json(raw)


def _clean_verdict(v):
    try:
        conf = float(v.get("confidence", 0.0))
    except (TypeError, ValueError):
        conf = 0.0
    if conf > 1.0:          # some models answer 0-100
        conf = conf / 100.0
    return bool(v.get("is_valid", False)), max(0.0, min(1.0, conf)), str(v.get("rationale", ""))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def verify_claims(problem, claims, context="", tau=None, mode=None):
    tau = cfg.VERIFICATION_THRESHOLD if tau is None else tau
    mode = (mode or cfg.VERIFIER_MODE).lower()
    claims = list(claims)

    deterministic = _deterministic(problem, claims) if mode in ("hybrid", "arithmetic") else {}

    llm = {}
    if mode in ("hybrid", "llm") and claims:
        if cfg.BATCH_VERIFY:
            try:
                llm = _llm_batch(problem, claims, mode)
            except Exception:
                llm = {}
        for i, claim in enumerate(claims):
            cid = claim["claim_id"]
            if cid in llm or cid in deterministic:
                continue
            try:
                llm[cid] = _llm_single(problem, claim, claims[:i], mode)
            except Exception as e:
                llm[cid] = {"is_valid": True, "confidence": 0.0,
                            "rationale": f"verifier error: {e}", "_error": True}

    results = []
    for claim in claims:
        cid = claim["claim_id"]
        if cid in deterministic:
            verdict = dict(deterministic[cid])
        elif cid in llm:
            valid, conf, why = _clean_verdict(llm[cid])
            verdict = {
                "is_valid": valid and conf >= tau,
                "confidence": conf,
                "rationale": why,
                "source": "llm_error" if llm[cid].get("_error") else "llm",
                "correct_value": None,
                "stated_value": None,
            }
            if cfg.VALUE_CHECK and not verdict["is_valid"] and not llm[cid].get("_error"):
                verdict = _value_check(claim, verdict, llm[cid].get("correct_value"))
        else:  # arithmetic-only mode and nothing found
            verdict = {"is_valid": True, "confidence": 1.0, "rationale": "No issue found.",
                       "source": "arithmetic", "correct_value": None, "stated_value": None}
        results.append({**claim, "claim_id": cid, **verdict})
    if cfg.PROGRAM_CHECK and results:
        results = _program_check(problem, results)
    return results


def _value_check(claim, verdict, correct_value):
    """Drop a flag whose 'correct' value is the value the claim already states."""
    from src.verification.program_check import _value, same_value
    try:
        correct = None if correct_value is None else float(correct_value)
    except (TypeError, ValueError):
        correct = None
    stated = _value(claim["text"])
    verdict = {**verdict, "correct_value": correct, "stated_value": stated}
    if correct is not None and stated is not None and same_value(correct, stated):
        verdict.update(is_valid=True, overruled_by="value_check",
                       rationale="[overruled: judge's correct value equals the stated value] "
                                 + verdict["rationale"])
    return verdict


def _program_check(problem, results):
    """Compare the plan's answer with an independent Python solution."""
    from src.verification.program_check import (agrees, locate_error, plan_answer,
                                                program_answer, _fmt)
    prog = program_answer(problem)
    if prog is None:
        return results
    results = [dict(v, program_answer=prog) for v in results]
    if agrees(results, prog):
        # Independent agreement: flags that only the LLM judge raised are dropped.
        for v in results:
            if not v["is_valid"] and v.get("source") in ("llm", "llm_error"):
                v.update(is_valid=True, overruled_by="program",
                         rationale="[overruled: independent program agrees with the plan] "
                                   + v.get("rationale", ""))
        return results
    plan_val = plan_answer(results)
    if plan_val is None:
        return results   # the plan states no final value to compare
    cid, why = locate_error(problem, results, plan_val, prog)
    if cid is None:
        return results
    evidence = (f"An independent calculation gives {_fmt(prog)}, but the plan concludes "
                f"{_fmt(plan_val)}. {why}").strip()
    for v in results:
        if v["claim_id"] == cid:
            if v["is_valid"]:
                v.update(is_valid=False, confidence=0.9, source="program",
                         rationale=evidence, correct_value=None)
            else:
                v["rationale"] = evidence + " " + v.get("rationale", "")
            break
    return results


def verify_claim(problem, claim, context="", tau=None):
    """Single-claim helper kept for older scripts."""
    return verify_claims(problem, [claim], context=context, tau=tau)[0]


def failed(verification):
    return [v for v in verification if not v.get("is_valid", False)]
