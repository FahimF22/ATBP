"""
A2: Verification + Full Regeneration.

When verification detects failed claims in Agent A's output:
- Discard the entire Agent A plan
- Regenerate a completely new Agent A plan
- Verify the new plan
- Repeat up to MAX_REGENERATIONS times
- If a valid plan is produced, continue to Agent B and C
- If all regenerations fail, return failure record

This strategy prioritizes correctness over efficiency.
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
from evaluation.gsm8k_evaluator import evaluate_answer
from logging_system.experiment_logger import save_experiment
from config.config import VERIFICATION_THRESHOLD, MAX_REGENERATIONS


STRATEGY = "a2_full_regeneration"


def run_a2_full(problem):
    """
    A2 with full pipeline:
    1. Generate Agent A plan
    2. Verify all claims
    3. If all valid, continue to Agent B and C
    4. If any invalid, discard entire plan and regenerate
    5. Repeat until valid or max attempts reached
    6. Return final answer
    """

    start_time = time.time()

    plan = None
    claims_final = None
    verification_final = None
    regeneration_attempts = 0
    success = False
    failure_reason = None

    # Try up to MAX_REGENERATIONS + 1 times (initial + regenerations)
    for attempt in range(MAX_REGENERATIONS + 1):
        regeneration_attempts = attempt

        # Generate Agent A plan
        plan = agent_a(problem)

        # Extract atomic claims from plan
        try:
            claims = extract_claims(problem=problem, reasoning=plan)
        except Exception as e:
            claims = []

        if not claims:
            failure_reason = "no_claims_extracted"
            if attempt < MAX_REGENERATIONS:
                continue
            else:
                break

        # Verify all claims
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

        # If all claims are valid, accept the plan
        if not failed_claims:
            claims_final = claims
            verification_final = verification
            success = True
            break

        # Otherwise, discard the plan and regenerate
        failure_reason = f"verification_failed_{len(failed_claims)}_claims"

        if attempt == MAX_REGENERATIONS:
            # Out of attempts
            break

    # If we have a valid plan, continue to Agent B and C
    if success and plan:
        try:
            b_output = agent_b(problem, plan)
        except Exception as e:
            b_output = f"[Error in Agent B: {str(e)}]"

        try:
            c_output = agent_c(problem, plan, b_output)
        except Exception as e:
            c_output = f"[Error in Agent C: {str(e)}]"
    else:
        b_output = None
        c_output = None

    latency = time.time() - start_time

    return {
        "strategy": STRATEGY,
        "problem": problem,
        "success": success,
        "failure_reason": failure_reason,
        "regeneration_attempts": regeneration_attempts,
        "agent_a": plan,
        "agent_b": b_output,
        "agent_c": c_output,
        "claims": claims_final or [],
        "verification": verification_final or [],
        "latency_seconds": latency,
    }


def main(num_examples=5):
    """Run A2 on num_examples from GSM8K test set."""

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

        result = run_a2_full(problem)

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
            "agent_a": result["agent_a"],
            "agent_b": result["agent_b"],
            "agent_c": result["agent_c"],
            "prediction": prediction,
            "correct": is_correct,
            "regeneration_attempts": result["regeneration_attempts"],
            "success": result["success"],
            "failure_reason": result["failure_reason"],
            "claims": result["claims"],
            "verification": result["verification"],
            "latency_seconds": result["latency_seconds"],
        }

        save_experiment(record, filename="results/a2_full_regeneration.jsonl")

        print(f"Correct: {is_correct}")
        print(f"Regenerations: {result['regeneration_attempts']}")
        print(f"Latency: {result['latency_seconds']:.2f}s")

    if processed > 0:
        accuracy = correct / processed
    else:
        accuracy = 0.0

    print("\n" + "=" * 70)
    print("A2 RESULTS")
    print("=" * 70)
    print(f"Examples: {processed}")
    print(f"Correct: {correct}")
    print(f"Accuracy: {accuracy:.4f}")


if __name__ == "__main__":
    main(num_examples=5)  # Start with smoke test
