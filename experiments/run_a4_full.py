"""
A4: Adaptive Targeted Recovery.

Uses verification results and dependency information to adaptively select
the recovery scope:

- No Recovery: All claims verify successfully
- Isolated Claim Repair: Single claim failed, no dependents
- Dependency Branch Repair: Multiple failures traced to shared dependency
- Agent-Level Regeneration: Multiple scattered failures
- Full Regeneration: >50% of claims failed

This strategy balances efficiency and correctness by selecting the minimal
necessary recovery scope.
"""

import sys
import time
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from datasets import load_dataset

from agents.agent_a import agent_a
from agents.agent_b import agent_b
from agents.agent_c import agent_c
from src.verification.claim_extractor import extract_claims
from src.verification.claim_verifier import verify_claims
from src.recovery.dependency import build_dependency_graph
from src.recovery.adaptive_scope_selector import select_recovery_scope
from src.recovery.llm_recovery import regenerate_plan, repair_claim
from evaluation.gsm8k_evaluator import evaluate_answer
from logging_system.experiment_logger import save_experiment
from config.config import VERIFICATION_THRESHOLD, MAX_REGENERATIONS


STRATEGY = "a4_adaptive_recovery"


def reconstruct_plan(claims):
    """Reconstruct plan from claims."""
    return "\n".join(c.get("text", "") for c in claims if c.get("text"))


def run_a4_full(problem):
    """
    A4 with adaptive scope selection and full pipeline.

    1. Generate Agent A plan
    2. Verify all claims
    3. Build dependency graph
    4. Adaptively select recovery scope
    5. Apply recovery (no action, repair, or regenerate)
    6. Continue to Agent B and C
    7. Return final answer
    """

    start_time = time.time()

    # Generate initial plan
    try:
        plan = agent_a(problem)
    except Exception as e:
        plan = f"[Error in Agent A: {str(e)}]"

    # Extract claims
    try:
        claims = extract_claims(problem=problem, reasoning=plan)
    except Exception as e:
        claims = []

    if not claims:
        return {
            "strategy": STRATEGY,
            "problem": problem,
            "success": False,
            "failure_reason": "no_claims_extracted",
            "agent_a_original": plan,
            "agent_a_final": None,
            "agent_b": None,
            "agent_c": None,
            "claims_initial": [],
            "claims_final": [],
            "verification_initial": [],
            "verification_final": [],
            "recovery_scope": "none",
            "regeneration_attempts": 0,
            "repair_attempts": 0,
            "latency_seconds": time.time() - start_time,
        }

    # Verify initial claims
    try:
        verification = verify_claims(
            problem=problem,
            claims=claims,
            context=plan,
            tau=VERIFICATION_THRESHOLD,
        )
    except Exception as e:
        verification = []

    # Build dependency graph
    try:
        dep_graph = build_dependency_graph(claims)
    except Exception as e:
        dep_graph = None

    # Select recovery scope adaptively
    try:
        scope_decision = select_recovery_scope(
            claims=claims,
            verification=verification,
            dependency_graph=dep_graph,
            tau=VERIFICATION_THRESHOLD,
        )
    except Exception as e:
        scope_decision = {
            "scope": "full_regeneration",
            "target_claim_ids": [],
            "failed_count": 0,
            "rationale": f"Scope selection error: {str(e)}",
        }

    scope = scope_decision.get("scope", "no_recovery")
    regeneration_attempts = 0
    repair_attempts = 0
    final_plan = plan
    final_claims = claims
    final_verification = verification

    # Apply recovery based on selected scope
    if scope == "no_recovery":
        # All claims valid; proceed without recovery
        pass

    elif scope == "isolated_claim":
        # Repair single failed claim
        failed_id = scope_decision.get("target_claim_ids", [None])[0]
        if failed_id:
            for claim in claims:
                if claim.get("claim_id") == failed_id:
                    try:
                        repair_attempts = 1
                        repaired_text = repair_claim(
                            problem=problem,
                            claim=claim,
                            rationale="",
                        )
                        claim["text"] = repaired_text
                        claim["was_repaired"] = True
                    except Exception as e:
                        pass
                    break

        final_plan = reconstruct_plan(claims)
        final_claims = claims

        # Reverify
        try:
            final_verification = verify_claims(
                problem=problem,
                claims=final_claims,
                context=final_plan,
                tau=VERIFICATION_THRESHOLD,
            )
        except Exception as e:
            final_verification = []

    elif scope == "dependency_branch":
        # Repair failed claim and all affected dependents
        target_ids = set(scope_decision.get("target_claim_ids", []))
        repair_attempts = len(target_ids)

        for claim in claims:
            if claim.get("claim_id") in target_ids:
                try:
                    repaired_text = repair_claim(
                        problem=problem,
                        claim=claim,
                        rationale="",
                    )
                    claim["text"] = repaired_text
                    claim["was_repaired"] = True
                except Exception as e:
                    pass

        final_plan = reconstruct_plan(claims)
        final_claims = claims

        # Reverify
        try:
            final_verification = verify_claims(
                problem=problem,
                claims=final_claims,
                context=final_plan,
                tau=VERIFICATION_THRESHOLD,
            )
        except Exception as e:
            final_verification = []

    elif scope == "agent_level":
        # Regenerate entire Agent A
        for attempt in range(MAX_REGENERATIONS):
            regeneration_attempts = attempt + 1

            try:
                final_plan = regenerate_plan(problem)
            except Exception as e:
                final_plan = plan
                continue

            try:
                final_claims = extract_claims(
                    problem=problem, reasoning=final_plan
                )
            except Exception as e:
                final_claims = []
                continue

            if not final_claims:
                continue

            try:
                final_verification = verify_claims(
                    problem=problem,
                    claims=final_claims,
                    context=final_plan,
                    tau=VERIFICATION_THRESHOLD,
                )
            except Exception as e:
                final_verification = []
                continue

            # Check if regeneration succeeded
            failed = [
                v for v in final_verification
                if not v.get("is_valid", False)
            ]

            if not failed:
                break

    elif scope == "full_regeneration":
        # Discard entire pipeline and regenerate
        for attempt in range(MAX_REGENERATIONS):
            regeneration_attempts = attempt + 1

            try:
                final_plan = regenerate_plan(problem)
            except Exception as e:
                final_plan = plan
                continue

            try:
                final_claims = extract_claims(
                    problem=problem, reasoning=final_plan
                )
            except Exception as e:
                final_claims = []
                continue

            if not final_claims:
                continue

            try:
                final_verification = verify_claims(
                    problem=problem,
                    claims=final_claims,
                    context=final_plan,
                    tau=VERIFICATION_THRESHOLD,
                )
            except Exception as e:
                final_verification = []
                continue

            # Check if regeneration succeeded
            failed = [
                v for v in final_verification
                if not v.get("is_valid", False)
            ]

            if not failed:
                break

    # Continue pipeline with final plan
    try:
        b_output = agent_b(problem, final_plan)
    except Exception as e:
        b_output = f"[Error in Agent B: {str(e)}]"

    try:
        c_output = agent_c(problem, final_plan, b_output)
    except Exception as e:
        c_output = f"[Error in Agent C: {str(e)}]"

    latency = time.time() - start_time

    return {
        "strategy": STRATEGY,
        "problem": problem,
        "success": True,
        "agent_a_original": plan,
        "agent_a_final": final_plan,
        "agent_b": b_output,
        "agent_c": c_output,
        "claims_initial": claims,
        "claims_final": final_claims,
        "verification_initial": verification,
        "verification_final": final_verification,
        "recovery_scope": scope,
        "recovery_rationale": scope_decision.get("rationale", ""),
        "regeneration_attempts": regeneration_attempts,
        "repair_attempts": repair_attempts,
        "latency_seconds": latency,
    }


def main(num_examples=5):
    """Run A4 on num_examples from GSM8K test set."""

    dataset = load_dataset("openai/gsm8k", "main", split="test")

    correct = 0
    processed = 0

    for i in range(min(num_examples, len(dataset))):
        item = dataset[i]
        problem = item["question"]
        ground_truth = item["answer"]

        print("\n" + "=" * 70)
        print(f"Problem {i + 1}/{num_examples}")
        print("=" * 70)

        result = run_a4_full(problem)

        # Evaluate final answer
        is_correct, prediction, gt = evaluate_answer(result["agent_c"], ground_truth)

        if is_correct:
            correct += 1

        processed += 1

        record = {
            "problem_id": i,
            "strategy": STRATEGY,
            "problem": problem,
            "ground_truth": gt,
            "agent_a_original": result["agent_a_original"],
            "agent_a_final": result["agent_a_final"],
            "agent_b": result["agent_b"],
            "agent_c": result["agent_c"],
            "prediction": prediction,
            "correct": is_correct,
            "recovery_scope": result["recovery_scope"],
            "recovery_rationale": result.get("recovery_rationale", ""),
            "regeneration_attempts": result["regeneration_attempts"],
            "repair_attempts": result["repair_attempts"],
            "claims_initial": result["claims_initial"],
            "claims_final": result["claims_final"],
            "verification_initial": result["verification_initial"],
            "verification_final": result["verification_final"],
            "latency_seconds": result["latency_seconds"],
        }

        save_experiment(record, filename="results/a4_adaptive_recovery.jsonl")

        print(f"Correct: {is_correct}")
        print(f"Recovery scope: {result['recovery_scope']}")
        print(f"Regenerations: {result['regeneration_attempts']}")
        print(f"Repairs: {result['repair_attempts']}")
        print(f"Latency: {result['latency_seconds']:.2f}s")

    if processed > 0:
        accuracy = correct / processed
    else:
        accuracy = 0.0

    print("\n" + "=" * 70)
    print("A4 RESULTS")
    print("=" * 70)
    print(f"Examples: {processed}")
    print(f"Correct: {correct}")
    print(f"Accuracy: {accuracy:.4f}")


if __name__ == "__main__":
    main(num_examples=5)  # Start with smoke test
