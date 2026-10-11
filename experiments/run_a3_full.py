"""
A3: Verification + Fixed Targeted Repair.

When verification detects failed claims in Agent A's output:
- Identify ONLY the failed claims
- Repair each failed claim individually (one attempt per claim)
- Keep valid claims unchanged (critical property of A3)
- Reconstruct the plan from original valid + repaired claims
- Verify the repaired claims
- Continue to Agent B and C with the repaired plan

This strategy prioritizes efficiency while maintaining reasoning quality.
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
from src.recovery.llm_recovery import repair_claim
from evaluation.gsm8k_evaluator import evaluate_answer
from logging_system.experiment_logger import save_experiment
from config.config import VERIFICATION_THRESHOLD


STRATEGY = "a3_targeted_repair"


def reconstruct_plan(claims):
    """Reconstruct plan from verified/repaired claims."""
    return "\n".join(c.get("text", "") for c in claims if c.get("text"))


def run_a3_full(problem):
    """
    A3 with full pipeline:
    1. Generate Agent A plan
    2. Verify all claims
    3. Repair only FAILED claims (one attempt each)
    4. Verify repaired claims
    5. Continue to Agent B and C with repaired plan
    6. Return final answer
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
            "agent_a_repaired": None,
            "agent_b": None,
            "agent_c": None,
            "claims_initial": [],
            "claims_repaired": [],
            "verification_before": [],
            "verification_after": [],
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

    failed_claims = [v for v in verification if not v.get("is_valid", False)]

    # If no failures, skip repair and continue to B and C
    if not failed_claims:
        try:
            b_output = agent_b(problem, plan)
        except Exception as e:
            b_output = f"[Error in Agent B: {str(e)}]"

        try:
            c_output = agent_c(problem, plan, b_output)
        except Exception as e:
            c_output = f"[Error in Agent C: {str(e)}]"

        latency = time.time() - start_time

        return {
            "strategy": STRATEGY,
            "problem": problem,
            "success": True,
            "failure_reason": None,
            "agent_a_original": plan,
            "agent_a_repaired": plan,
            "agent_b": b_output,
            "agent_c": c_output,
            "claims_initial": claims,
            "claims_repaired": claims,
            "verification_before": verification,
            "verification_after": verification,
            "repair_attempts": 0,
            "latency_seconds": latency,
        }

    # Repair failed claims
    repaired_claims = []
    repair_count = 0

    for claim in verification:
        if not claim.get("is_valid", False):
            # This claim failed; attempt repair
            repair_count += 1
            try:
                repaired_text = repair_claim(
                    problem=problem,
                    claim=claim,
                    rationale=claim.get("rationale", ""),
                )
            except Exception as e:
                repaired_text = claim.get("text", "")

            repaired_claims.append(
                {
                    "claim_id": claim.get("claim_id"),
                    "text": repaired_text,
                    "original_text": claim.get("text"),
                    "was_repaired": True,
                }
            )
        else:
            # Valid claim passes through unchanged (critical for A3)
            repaired_claims.append(
                {
                    "claim_id": claim.get("claim_id"),
                    "text": claim.get("text"),
                    "original_text": claim.get("text"),
                    "was_repaired": False,
                }
            )

    # Reconstruct plan from repaired claims
    repaired_plan = reconstruct_plan(repaired_claims)

    # Verify repaired plan
    try:
        verification_after = verify_claims(
            problem=problem,
            claims=repaired_claims,
            context=repaired_plan,
            tau=VERIFICATION_THRESHOLD,
        )
    except Exception as e:
        verification_after = []

    # Continue pipeline with repaired plan
    try:
        b_output = agent_b(problem, repaired_plan)
    except Exception as e:
        b_output = f"[Error in Agent B: {str(e)}]"

    try:
        c_output = agent_c(problem, repaired_plan, b_output)
    except Exception as e:
        c_output = f"[Error in Agent C: {str(e)}]"

    latency = time.time() - start_time

    return {
        "strategy": STRATEGY,
        "problem": problem,
        "success": True,
        "failure_reason": None,
        "agent_a_original": plan,
        "agent_a_repaired": repaired_plan,
        "agent_b": b_output,
        "agent_c": c_output,
        "claims_initial": claims,
        "claims_repaired": repaired_claims,
        "verification_before": verification,
        "verification_after": verification_after,
        "repair_attempts": repair_count,
        "latency_seconds": latency,
    }


def main(num_examples=5):
    """Run A3 on num_examples from GSM8K test set."""

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

        result = run_a3_full(problem)

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
            "agent_a_repaired": result["agent_a_repaired"],
            "agent_b": result["agent_b"],
            "agent_c": result["agent_c"],
            "prediction": prediction,
            "correct": is_correct,
            "repair_attempts": result["repair_attempts"],
            "claims_initial": result["claims_initial"],
            "claims_repaired": result["claims_repaired"],
            "verification_before": result["verification_before"],
            "verification_after": result["verification_after"],
            "latency_seconds": result["latency_seconds"],
        }

        save_experiment(record, filename="results/a3_targeted_repair.jsonl")

        print(f"Correct: {is_correct}")
        print(f"Repair attempts: {result['repair_attempts']}")
        print(f"Latency: {result['latency_seconds']:.2f}s")

    if processed > 0:
        accuracy = correct / processed
    else:
        accuracy = 0.0

    print("\n" + "=" * 70)
    print("A3 RESULTS")
    print("=" * 70)
    print(f"Examples: {processed}")
    print(f"Correct: {correct}")
    print(f"Accuracy: {accuracy:.4f}")


if __name__ == "__main__":
    main(num_examples=5)  # Start with smoke test
