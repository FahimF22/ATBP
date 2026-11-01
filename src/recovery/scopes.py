"""
The four ATBP recovery scopes and the adaptive (A4) policy.

All scopes take the same input -- the problem, Agent A's plan, its claims and
their verification -- and return a RecoveryResult with the plan that is passed
on to Agents B and C.

  isolated  : repair only the claims that failed verification
  branch    : repair the failed claims, then recompute every claim that
              depends on them (dependency-aware backtracking)
  agent     : regenerate Agent A, telling it which steps were wrong
              (localized feedback)
  full      : restart Agent A from scratch with no feedback (blind restart)

"agent" and "full" both produce a new plan; they differ in whether the error
location is used. Verification runs after Agent A only, so Agents B and C are
run once on whatever plan recovery returns.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from config import config as cfg
from agents.agent_a import agent_a
from src.recovery.dependency import build_dependency_graph
from src.recovery.llm_recovery import repair_claim, rederive_claim
from src.verification.arithmetic_checker import (
    check_arithmetic,
    fix_arithmetic,
    fmt_number,
    normalize,
)
from src.verification.claim_extractor import extract_claims, claims_to_plan
from src.verification.claim_verifier import verify_claims, failed


SCOPES = ("isolated", "branch", "agent", "full")


@dataclass
class RecoveryResult:
    scope: str
    plan: str
    claims: list
    verification: list
    changed_ids: list = field(default_factory=list)   # claims rewritten (claim scopes)
    discarded: bool = False                           # whole plan replaced
    repair_attempts: int = 0                          # claim repairs/rederivations
    regeneration_attempts: int = 0
    successful_attempts: int = 0                      # attempts accepted on re-verification
    method_counts: dict = field(default_factory=dict)
    notes: str = ""


def safe_graph(claims):
    try:
        return build_dependency_graph(claims)
    except Exception:
        return build_dependency_graph(
            [{"claim_id": c["claim_id"], "text": c["text"], "depends_on": []} for c in claims]
        )


def _bump(counts, key):
    counts[key] = counts.get(key, 0) + 1


# ---------------------------------------------------------------------------
# Claim-level helpers
# ---------------------------------------------------------------------------

def claim_value(text):
    """The value a claim concludes with: first number after the last '='."""
    norm = normalize(text)
    if "=" not in norm:
        return None
    tail = norm.rsplit("=", 1)[1]
    m = re.search(r"-?\$?\d[\d,]*(?:\.\d+)?", tail)
    if not m:
        return None
    try:
        return float(m.group(0).replace("$", "").replace(",", ""))
    except ValueError:
        return None


def _repair_one(problem, claim, verdict, earlier, counts):
    """Repair one failed claim. Arithmetic faults are fixed exactly."""
    if verdict.get("source") == "arithmetic":
        fixed, changes = fix_arithmetic(claim["text"])
        if changes:
            _bump(counts, "arithmetic_fix")
            return fixed
    _bump(counts, "llm_repair")
    text = repair_claim(problem, claim, verdict.get("rationale", ""), earlier)
    fixed, changes = fix_arithmetic(text)   # the repair itself may miscalculate
    return fixed if changes else text


def _substitute(text, changes):
    """
    Replace stale input values in a dependent claim. Only operands (text
    before the last '=') are replaced; results are then recomputed.
    Returns (new_text, replaced?). replaced is None when it is ambiguous which
    occurrence is stale (e.g. "2 + 2" where only one 2 changed); the caller
    then falls back to an LLM rederivation.
    """
    norm = normalize(text)
    if "=" in norm:
        head, tail = norm.rsplit("=", 1)
    else:
        head, tail = norm, None
    replaced = False
    for old, new in changes.items():
        old_s, new_s = fmt_number(old), fmt_number(new)
        pattern = rf"(?<![\d.]){re.escape(old_s)}(?:\.0+)?(?![\d.]*\d)"
        hits = len(re.findall(pattern, head))
        if hits > 1:
            return text, None
        if hits == 1:
            head = re.sub(pattern, new_s, head)
            replaced = True
        else:
            # "1,000" style
            with_commas = f"{int(old):,}" if old == int(old) and abs(old) >= 1000 else None
            if with_commas and with_commas in head:
                head = head.replace(with_commas, new_s)
                replaced = True
    if not replaced:
        return text, False
    out = head if tail is None else f"{head}={tail}"
    fixed, _ = fix_arithmetic(out)
    return fixed, True


# ---------------------------------------------------------------------------
# Scopes
# ---------------------------------------------------------------------------

def _reverify(problem, claims):
    return verify_claims(problem, claims, context=claims_to_plan(claims))


def recover_isolated(problem, plan, claims, verification, targets=None):
    counts = {}
    by_id = {v["claim_id"]: v for v in verification}
    targets = targets or [v["claim_id"] for v in failed(verification)]
    new_claims = [dict(c) for c in claims]
    changed = []
    for i, c in enumerate(new_claims):
        if c["claim_id"] not in targets:
            continue
        new_text = _repair_one(problem, c, by_id.get(c["claim_id"], {}), new_claims[:i], counts)
        if new_text.strip() != c["text"].strip():
            changed.append(c["claim_id"])
        c["text"] = new_text
    new_ver = _reverify(problem, new_claims)
    ok_ids = {v["claim_id"] for v in new_ver if v["is_valid"]}
    return RecoveryResult(
        scope="isolated", plan=claims_to_plan(new_claims), claims=new_claims,
        verification=new_ver, changed_ids=changed, repair_attempts=len(targets),
        successful_attempts=sum(1 for t in targets if t in ok_ids),
        method_counts=counts,
    )


def recover_branch(problem, plan, claims, verification, targets=None, graph=None):
    counts = {}
    graph = graph or safe_graph(claims)
    by_id = {v["claim_id"]: v for v in verification}
    targets = targets or [v["claim_id"] for v in failed(verification)]
    affected = set(targets)
    for t in targets:
        if t in graph.nodes:
            affected |= graph.downstream(t)

    new_claims = [dict(c) for c in claims]
    index = {c["claim_id"]: i for i, c in enumerate(new_claims)}
    value_changes = {}   # old value -> corrected value
    changed = []
    attempts = 0

    # Claims are in reasoning order and only depend on earlier claims,
    # so a single forward pass is a topological order.
    for i, c in enumerate(new_claims):
        cid = c["claim_id"]
        if cid not in affected:
            continue
        attempts += 1
        old_text = c["text"]
        old_val = claim_value(old_text)
        if cid in targets:
            new_text = _repair_one(problem, c, by_id.get(cid, {}), new_claims[:i], counts)
        else:
            new_text, done = _substitute(old_text, value_changes)
            if done:
                _bump(counts, "value_propagation")
            else:
                prereq_ids = graph.direct_prerequisites(cid) if cid in graph.nodes else set()
                prereqs = [new_claims[index[p]] for p in sorted(prereq_ids, key=index.get) if p in index]
                if any(p in changed for p in prereq_ids):
                    _bump(counts, "llm_rederive")
                    new_text = rederive_claim(problem, c, prereqs)
                    fixed, ch = fix_arithmetic(new_text)
                    new_text = fixed if ch else new_text
                else:
                    new_text = old_text   # prerequisites unchanged: nothing to redo
        new_val = claim_value(new_text)
        if old_val is not None and new_val is not None and abs(old_val - new_val) > 1e-9:
            value_changes[old_val] = new_val
        if new_text.strip() != old_text.strip():
            changed.append(cid)
        c["text"] = new_text

    new_ver = _reverify(problem, new_claims)
    ok_ids = {v["claim_id"] for v in new_ver if v["is_valid"]}
    return RecoveryResult(
        scope="branch", plan=claims_to_plan(new_claims), claims=new_claims,
        verification=new_ver, changed_ids=changed, repair_attempts=attempts,
        successful_attempts=sum(1 for t in affected if t in ok_ids),
        method_counts=counts, notes=f"affected={sorted(affected, key=lambda x: index.get(x, 0))}",
    )


def _feedback(verification):
    lines = []
    for v in failed(verification):
        lines.append(f'- "{v["text"]}": {v.get("rationale", "")}')
    return "\n".join(lines)


def _regenerate(problem, verification, use_feedback, scope):
    """Sample new Agent A plans until one passes verification."""
    feedback = _feedback(verification) if use_feedback else None
    best = None
    successes = 0
    attempts = 0
    for k in range(cfg.MAX_REGENERATIONS):
        attempts = k + 1
        seed = cfg.BASE_SEED + 1000 * (1 if use_feedback else 2) + k
        plan = agent_a(problem, feedback=feedback,
                       temperature=cfg.REGEN_TEMPERATURE, seed=seed)
        try:
            claims = extract_claims(problem, plan)
        except Exception:
            claims = []
        if not claims:
            continue
        ver = verify_claims(problem, claims, context=plan)
        n_fail = len(failed(ver))
        if best is None or n_fail < best[0]:
            best = (n_fail, plan, claims, ver)
        if n_fail == 0:
            successes += 1
            break
    if best is None:
        return None, attempts, successes
    _, plan, claims, ver = best
    return (plan, claims, ver), attempts, successes


def recover_regenerate(problem, plan, claims, verification, use_feedback):
    scope = "agent" if use_feedback else "full"
    out, attempts, successes = _regenerate(problem, verification, use_feedback, scope)
    if out is None:   # every attempt failed to produce claims: keep original
        return RecoveryResult(scope=scope, plan=plan, claims=claims, verification=verification,
                              regeneration_attempts=attempts, notes="regeneration produced nothing")
    new_plan, new_claims, new_ver = out
    return RecoveryResult(
        scope=scope, plan=new_plan, claims=new_claims, verification=new_ver,
        discarded=True, regeneration_attempts=attempts, successful_attempts=successes,
    )


def apply_scope(scope, problem, plan, claims, verification, targets=None, graph=None):
    if scope == "isolated":
        return recover_isolated(problem, plan, claims, verification, targets)
    if scope == "branch":
        return recover_branch(problem, plan, claims, verification, targets, graph)
    if scope == "agent":
        return recover_regenerate(problem, plan, claims, verification, use_feedback=True)
    if scope == "full":
        return recover_regenerate(problem, plan, claims, verification, use_feedback=False)
    if scope == "none":
        return RecoveryResult(scope="none", plan=plan, claims=claims, verification=verification)
    raise ValueError(f"Unknown scope {scope}")


# ---------------------------------------------------------------------------
# Adaptive policy (A4)
# ---------------------------------------------------------------------------

def fault_features(claims, verification, graph=None):
    """Feature vector x_f for each failed claim (paper Sec. V-F)."""
    graph = graph or safe_graph(claims)
    n = max(len(claims), 1)
    out = []
    for v in failed(verification):
        cid = v["claim_id"]
        if cid not in graph.nodes:
            continue
        down = graph.downstream(cid)
        up = graph.upstream(cid)
        out.append({
            "claim_id": cid,
            "confidence": v.get("confidence", 0.0),
            "source": v.get("source"),
            "depth": graph.dependency_depth(cid),
            "n_down": len(down),
            "n_up": len(up),
            "position": round([c["claim_id"] for c in claims].index(cid) / n, 3),
            "branch_cost": (1 + len(down)) / n,   # share of claims a branch repair touches
        })
    return out


def select_scope(claims, verification, graph=None):
    """
    Rule-based policy pi(x_f). Returns (scope, targets, rationale, features).

    1. Nothing failed                         -> none
    2. Most claims failed                     -> full (plan is broken overall)
    3. Independent faults are many (>= 3)     -> agent (regenerate with feedback)
    4. No failed claim has dependents          -> isolated
    5. Branch would touch most of the plan    -> agent (cheaper/cleaner to redo)
    6. Otherwise                              -> branch
    """
    graph = graph or safe_graph(claims)
    feats = fault_features(claims, verification, graph)
    fails = failed(verification)
    n = max(len(claims), 1)
    if not fails:
        return "none", [], "All claims accepted.", feats

    failed_ids = {v["claim_id"] for v in fails}
    roots = [f for f in feats if not (graph.upstream(f["claim_id"]) & failed_ids)]
    affected = set(failed_ids)
    for f in feats:
        affected |= graph.downstream(f["claim_id"])
    fail_rate = len(fails) / n
    targets = sorted(failed_ids, key=lambda x: [c["claim_id"] for c in claims].index(x))

    if fail_rate >= cfg.FULL_REGEN_FAILURE_RATE:
        return "full", targets, f"{fail_rate:.0%} of claims failed; plan looks broken.", feats
    if len(roots) >= 3:
        return "agent", targets, f"{len(roots)} independent faults; regenerate Agent A with feedback.", feats
    if all(f["n_down"] == 0 for f in feats):
        return "isolated", targets, "Failed claims have no dependents; repair them only.", feats
    if len(affected) / n >= cfg.BRANCH_COST_RATIO:
        return "agent", targets, (f"Branch would recompute {len(affected)}/{n} claims; "
                                  "regenerating Agent A with feedback instead."), feats
    return "branch", targets, f"Repair {len(failed_ids)} claim(s) and recompute {len(affected) - len(failed_ids)} dependent(s).", feats
