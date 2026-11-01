"""
The evaluated systems, all built on one shared code path.

    A0        A -> B -> C (no verification)
    A2        verify, then full regeneration (blind restart)
    A3        verify, then isolated claim repair
    A4        verify, then adaptive scope (ATBP)
    A_branch  verify, then always branch backtracking   (fixed-scope ablation)
    A_agent   verify, then always agent regeneration     (fixed-scope ablation)

Every system first generates Agent A's plan with the same greedy call, so with
the cache on they all start from the identical plan, claims and verification.
"""

from __future__ import annotations

import time

from agents.agent_a import agent_a
from agents.agent_b import agent_b
from agents.agent_c import agent_c
from evaluation.gsm8k_evaluator import evaluate_answer
from src.llm_client import track_usage, model_id
from src.recovery.scopes import apply_scope, select_scope, safe_graph, fault_features
from src.verification.claim_extractor import extract_claims
from src.verification.claim_verifier import verify_claims, failed
from config import config as cfg


FIXED_SCOPE = {"a2": "full", "a3": "isolated", "a_branch": "branch", "a_agent": "agent"}
SYSTEMS = ("a0", "a2", "a3", "a4", "a_branch", "a_agent")


def initial_state(problem):
    plan = agent_a(problem)
    try:
        claims = extract_claims(problem, plan)
    except Exception:
        claims = []
    verification = verify_claims(problem, claims, context=plan) if claims else []
    return plan, claims, verification


def finish(problem, plan):
    b = agent_b(problem, plan)
    c = agent_c(problem, plan, b)
    return b, c


def recover(system, problem, plan, claims, verification, targets=None):
    """
    Choose and apply a recovery scope. Returns (scope, RecoveryResult or None,
    rationale, features).
    """
    graph = safe_graph(claims) if claims else None
    feats = fault_features(claims, verification, graph) if claims else []
    if system == "a0" or not claims:
        return "none", None, "no verification" if system == "a0" else "no claims extracted", feats
    if system == "a4":
        scope, auto_targets, why, feats = select_scope(claims, verification, graph)
        targets = targets or auto_targets
    else:
        has_fault = bool(targets) or bool(failed(verification))
        scope = FIXED_SCOPE[system] if has_fault else "none"
        why = f"fixed scope {scope}" if has_fault else "All claims accepted."
    if scope == "none":
        return "none", None, why, feats
    result = apply_scope(scope, problem, plan, claims, verification, targets=targets, graph=graph)
    return scope, result, why, feats


def run_system(system, problem, ground_truth, problem_id=None, state=None, targets=None,
               extra=None):
    """
    Run one system on one problem.

    state: optional (plan, claims, verification) to start from instead of
           generating Agent A's plan (used for fault injection).
    targets: optional claim ids to treat as faulty (oracle localization).
    """
    wall = time.time()
    with track_usage() as usage:
        if state is None:
            plan, claims, verification = initial_state(problem) if system != "a0" else (agent_a(problem), [], [])
        else:
            plan, claims, verification = state
            if system == "a0":
                claims, verification = [], []
        scope, result, why, feats = recover(system, problem, plan, claims, verification, targets)
        final_plan = result.plan if result else plan
        # NO_HARM: a recovered plan that still fails verification is not trusted.
        no_harm_fallback = bool(cfg.NO_HARM and result and failed(result.verification))
        if no_harm_fallback:
            final_plan = plan
        b_out, c_out = finish(problem, final_plan)

    correct, prediction, gt = evaluate_answer(c_out, ground_truth)
    fail_ids = list(targets) if targets else [v["claim_id"] for v in failed(verification)]
    accepted_before = [v["claim_id"] for v in verification if v.get("is_valid")]
    if result is None:
        collateral = 0
    elif result.discarded:
        collateral = len(accepted_before)
    else:
        collateral = len(set(result.changed_ids) & set(accepted_before))

    record = {
        "system": system,
        "problem_id": problem_id,
        "model": model_id(),
        "verifier_mode": cfg.VERIFIER_MODE,
        "correct": bool(correct),
        "prediction": prediction,
        "ground_truth": gt,
        "scope": scope,
        "scope_rationale": why,
        "detected": bool(fail_ids),
        "n_claims": len(claims),
        "n_failed_initial": len(fail_ids),
        "failed_ids": fail_ids,
        "failed_sources": [v.get("source") for v in verification if v["claim_id"] in fail_ids],
        "features": feats,
        "accepted_before": len(accepted_before),
        "collateral_changed": collateral,
        "changed_ids": result.changed_ids if result else [],
        "discarded": bool(result and result.discarded),
        "repair_attempts": result.repair_attempts if result else 0,
        "regeneration_attempts": result.regeneration_attempts if result else 0,
        "successful_attempts": result.successful_attempts if result else 0,
        "recovery_methods": result.method_counts if result else {},
        "no_harm_fallback": no_harm_fallback,
        "final_all_valid": (not failed(result.verification)) if result else (not fail_ids if claims else None),
        "usage": usage,
        "wall_seconds": round(time.time() - wall, 2),
        "plan_initial": plan,
        "plan_final": final_plan,
        "agent_b": b_out,
        "agent_c": c_out,
        "claims_initial": claims,
        "verification_initial": verification,
        "verification_final": result.verification if result else verification,
    }
    if extra:
        record.update(extra)
    return record
