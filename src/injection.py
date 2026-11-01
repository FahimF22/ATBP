"""
Controlled fault injection into Agent A's claims.

Fault kinds
  arithmetic : a calculation gets a wrong result, e.g. "3 x 15 = 40"
  operand    : a quantity is copied wrongly from the problem, e.g. "3 x 18 = 54"
               (the arithmetic itself is consistent)

In both cases the wrong value is then carried into every dependent claim with
correct arithmetic, so the fault cascades the way a real early mistake would:
only the faulty claim itself is wrong, everything after it is "consistently
wrong".

Positions
  deep : the eligible claim with the most downstream dependents
  leaf : an eligible claim with no dependents
"""

from __future__ import annotations

import random
import re

from src.recovery.scopes import claim_value, safe_graph, _substitute
from src.verification.arithmetic_checker import (
    check_arithmetic,
    fix_arithmetic,
    fmt_number,
    normalize,
    problem_numbers,
)


KINDS = ("arithmetic", "operand")
POSITIONS = ("deep", "leaf")


def _wrong_value(value, rng):
    """A plausible but wrong replacement value."""
    for _ in range(20):
        if value == int(value) and abs(value) >= 1:
            v = int(value)
            choice = rng.choice(["add", "mul"])
            if choice == "add":
                delta = rng.choice([1, 2, 3, 5, 10]) * max(1, abs(v) // 20)
                new = v + rng.choice([-1, 1]) * delta
            else:
                new = round(v * rng.choice([0.5, 0.8, 1.25, 1.5, 2]))
        else:
            new = round(value * rng.choice([0.5, 0.8, 1.25, 1.5, 2]), 2)
        if new != value and new > 0:
            return float(new)
    return float(value + 1)


def _arith_eligible(claim):
    report = check_arithmetic(claim["text"])
    return report.checked > 0 and report.ok and claim_value(claim["text"]) is not None


def _operand_candidates(claim, pnums):
    report = check_arithmetic(claim["text"])
    if not (report.checked > 0 and report.ok):
        return []
    return [o for o in report.operands if round(o, 6) in pnums and o not in (0, 1)]


def choose_targets(problem, claims, kind, graph=None):
    """Return {position: claim_id} for eligible injection targets."""
    graph = graph or safe_graph(claims)
    pnums = problem_numbers(problem)
    if kind == "arithmetic":
        eligible = [c for c in claims if _arith_eligible(c)]
    else:
        eligible = [c for c in claims if _operand_candidates(c, pnums)]
    if not eligible:
        return {}
    down = {c["claim_id"]: len(graph.downstream(c["claim_id"])) for c in eligible}
    deep = max(eligible, key=lambda c: (down[c["claim_id"]], -claims.index(c)))
    out = {}
    if down[deep["claim_id"]] > 0:
        out["deep"] = deep["claim_id"]
    leaves = [c for c in eligible if down[c["claim_id"]] == 0]
    if leaves:
        out["leaf"] = leaves[-1]["claim_id"]
    return out


def inject(problem, claims, target_id, kind, seed=0, graph=None):
    """
    Return (corrupted_claims, info). info has the old/new values and the ids
    of the dependents the wrong value was carried into.
    """
    rng = random.Random(seed)
    graph = graph or safe_graph(claims)
    new_claims = [dict(c) for c in claims]
    idx = {c["claim_id"]: i for i, c in enumerate(new_claims)}
    target = new_claims[idx[target_id]]
    text = normalize(target["text"])
    head, tail = text.rsplit("=", 1) if "=" in text else (text, "")

    if kind == "arithmetic":
        old = claim_value(text)
        wrong = _wrong_value(old, rng)
        m = re.search(r"\d[\d,]*(?:\.\d+)?", tail)
        tail = tail[:m.start()] + fmt_number(wrong) + tail[m.end():]
        corrupted = f"{head}={tail}"
        changes = {old: wrong}
        detail = {"old_value": old, "new_value": wrong}
    elif kind == "operand":
        cands = _operand_candidates(target, problem_numbers(problem))
        operand = rng.choice(cands)
        wrong_operand = _wrong_value(operand, rng)
        corrupted, done = _substitute(text, {operand: wrong_operand})
        if not done:
            raise ValueError("operand not found in claim")
        old = claim_value(text)
        new = claim_value(corrupted)
        changes = {old: new} if old is not None and new is not None and old != new else {}
        detail = {"old_operand": operand, "new_operand": wrong_operand,
                  "old_value": old, "new_value": new}
    else:
        raise ValueError(kind)

    target["text"] = corrupted
    propagated = []
    downstream = graph.downstream(target_id)
    for c in new_claims[idx[target_id] + 1:]:
        if c["claim_id"] not in downstream or not changes:
            continue
        old_val = claim_value(c["text"])
        new_text, done = _substitute(c["text"], changes)
        if not done:
            continue
        new_val = claim_value(new_text)
        if old_val is not None and new_val is not None and old_val != new_val:
            changes[old_val] = new_val
        c["text"] = new_text
        propagated.append(c["claim_id"])

    info = {
        "target_id": target_id,
        "kind": kind,
        "original_text": claims[idx[target_id]]["text"],
        "corrupted_text": corrupted,
        "n_down": len(downstream),
        "depth": graph.dependency_depth(target_id),
        "propagated_ids": propagated,
        **detail,
    }
    return new_claims, info


def oracle_verification(claims, target_id, info):
    """Verification that marks exactly the injected claim as faulty."""
    if info["kind"] == "arithmetic":
        msg = check_arithmetic(info["corrupted_text"]).issues
        why = msg[0].message() if msg else "This step contains a calculation error."
        source = "arithmetic"
    else:
        why = (f"The value {fmt_number(info['new_operand'])} in this step was not copied "
               f"correctly from the problem.")
        source = "oracle"
    out = []
    for c in claims:
        bad = c["claim_id"] == target_id
        out.append({**c, "is_valid": not bad, "confidence": 1.0 if bad else 0.95,
                    "rationale": why if bad else "Oracle: correct.",
                    "source": source if bad else "oracle",
                    "correct_value": None, "stated_value": None})
    return out
