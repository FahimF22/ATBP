#!/usr/bin/env python
"""
Error Injection Test for A3 (Targeted Repair).

This script injects deliberate errors into Agent A's reasoning and tests
whether the A3 pipeline can:
  1. EXTRACT the injected error as an atomic claim
  2. VERIFY / detect the error (is_valid=False)
  3. REPAIR the error (produce a corrected claim)
  4. RECONSTRUCT a valid plan from valid + repaired claims
  5. Produce the CORRECT final answer via Agent B and C

Usage:
    python error_injection_test.py                    # run all crafted tests
    python error_injection_test.py --use-gsm8k 3        # also test on 3 real GSM8K problems
    python error_injection_test.py --verbose            # show full claim/repair details
"""

import sys
import json
import time
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from agents.agent_b import agent_b
from agents.agent_c import agent_c
from src.verification.claim_extractor import extract_claims
from src.verification.claim_verifier import verify_claims
from src.recovery.llm_recovery import repair_claim
from src.recovery.dependency import build_dependency_graph
from evaluation.gsm8k_evaluator import evaluate_answer


# ──────────────────────────────────────────────────────────────────────
# Hand-crafted test cases: problem + CORRECT reasoning + CORRUPTED reasoning
# ──────────────────────────────────────────────────────────────────────

CRAFTED_CASES = [
    {
        "name": "Arithmetic error (12-5=8 instead of 7)",
        "problem": (
            "John has 12 apples. He gives away 5 apples. "
            "How many apples does he have left?"
        ),
        "ground_truth": "#### 7",
        "correct_reasoning": (
            "John has 12 apples.\n"
            "He gives away 5 apples.\n"
            "To find how many remain, subtract: 12 - 5 = 7.\n"
            "John has 7 apples left."
        ),
        "corrupted_reasoning": (
            "John has 12 apples.\n"
            "He gives away 5 apples.\n"
            "To find how many remain, subtract: 12 - 5 = 8.\n"
            "John has 8 apples left."
        ),
        "error_description": "Wrong subtraction result: 12-5=8 (should be 7)",
    },
    {
        "name": "Wrong quantity (15 stamps instead of 3 packs)",
        "problem": (
            "Janet buys 3 packs of stamps. Each pack has 15 stamps. "
            "She gives 10 stamps to her friend. How many stamps "
            "does she have left?"
        ),
        "ground_truth": "#### 35",
        "correct_reasoning": (
            "Janet buys 3 packs of stamps.\n"
            "Each pack has 15 stamps.\n"
            "Total stamps: 3 * 15 = 45.\n"
            "She gives 10 stamps to her friend.\n"
            "Remaining stamps: 45 - 10 = 35."
        ),
        "corrupted_reasoning": (
            "Janet buys 3 packs of stamps.\n"
            "Each pack has 15 stamps.\n"
            "Total stamps: 3 * 15 = 40.\n"
            "She gives 10 stamps to her friend.\n"
            "Remaining stamps: 40 - 10 = 30."
        ),
        "error_description": "Wrong multiplication: 3*15=40 (should be 45) and propagated 40-10=30",
    },
    {
        "name": "Wrong operation (addition instead of subtraction)",
        "problem": (
            "A bakery has 50 loaves of bread at the start of the day. "
            "They sell 32 loaves during the day. How many loaves "
            "remain at the end of the day?"
        ),
        "ground_truth": "#### 18",
        "correct_reasoning": (
            "The bakery starts with 50 loaves.\n"
            "They sell 32 loaves during the day.\n"
            "To find remaining loaves: 50 - 32 = 18.\n"
            "18 loaves remain at the end of the day."
        ),
        "corrupted_reasoning": (
            "The bakery starts with 50 loaves.\n"
            "They sell 32 loaves during the day.\n"
            "To find remaining loaves: 50 + 32 = 82.\n"
            "82 loaves remain at the end of the day."
        ),
        "error_description": "Wrong operation: 50+32=82 instead of 50-32=18",
    },
    {
        "name": "Multiple errors in multi-step problem",
        "problem": (
            "A school has 250 students. 60% are girls. "
            "How many boys are there?"
        ),
        "ground_truth": "#### 100",
        "correct_reasoning": (
            "Total students: 250.\n"
            "60% are girls, so 40% are boys.\n"
            "Number of girls: 250 * 0.60 = 150.\n"
            "Number of boys: 250 - 150 = 100.\n"
            "There are 100 boys."
        ),
        "corrupted_reasoning": (
            "Total students: 250.\n"
            "60% are girls, so 40% are boys.\n"
            "Number of girls: 250 * 0.60 = 160.\n"
            "Number of boys: 250 - 160 = 90.\n"
            "There are 90 boys."
        ),
        "error_description": "Wrong multiplication 250*0.60=160 (should be 150) and propagated 250-160=90",
    },
    {
        "name": "Wrong initial value from problem",
        "problem": (
            "Tom has $80. He spends $25 on a book and $15 on a pen. "
            "How much money does he have left?"
        ),
        "ground_truth": "#### 40",
        "correct_reasoning": (
            "Tom starts with $80.\n"
            "He spends $25 on a book.\n"
            "He spends $15 on a pen.\n"
            "Total spent: 25 + 15 = 40.\n"
            "Remaining: 80 - 40 = 40.\n"
            "Tom has $40 left."
        ),
        "corrupted_reasoning": (
            "Tom starts with $80.\n"
            "He spends $25 on a book.\n"
            "He spends $15 on a pen.\n"
            "Total spent: 25 + 15 = 35.\n"
            "Remaining: 80 - 35 = 45.\n"
            "Tom has $45 left."
        ),
        "error_description": "Wrong addition 25+15=35 (should be 40) and propagated 80-35=45",
    },
]


# ──────────────────────────────────────────────────────────────────────
# Core test runner
# ──────────────────────────────────────────────────────────────────────

def run_a3_with_injected_error(
    problem: str,
    corrupted_reasoning: str,
    ground_truth: str,
    verbose: bool = False,
):
    """
    Run the A3 pipeline on a corrupted reasoning plan.

    Steps:
    1. Extract atomic claims from the corrupted reasoning
    2. Verify each claim against the problem
    3. Repair failed claims
    4. Reconstruct plan from valid + repaired claims
    5. Run Agent B and C with the reconstructed plan
    6. Evaluate the final answer

    Returns a detailed result dict.
    """
    result = {
        "problem": problem,
        "ground_truth": ground_truth,
        "corrupted_reasoning": corrupted_reasoning,
    }

    # ── Step 1: Extract claims ──
    print("    [1] Extracting claims...", end=" ", flush=True)
    try:
        claims = extract_claims(problem=problem, reasoning=corrupted_reasoning)
        print(f"OK ({len(claims)} claims)")
    except Exception as e:
        print(f"FAILED: {e}")
        result["error"] = f"Claim extraction failed: {e}"
        return result
    result["claims_extracted"] = claims

    if verbose:
        for c in claims:
            print(f"        {c['claim_id']}: {c['text']}")

    # ── Step 2: Verify claims ──
    print("    [2] Verifying claims...", end=" ", flush=True)
    try:
        verification = verify_claims(
            problem=problem,
            claims=claims,
            context=corrupted_reasoning,
            tau=0.80,
        )
        print("OK")
    except Exception as e:
        print(f"FAILED: {e}")
        result["error"] = f"Verification failed: {e}"
        return result
    result["verification"] = verification

    failed_claims = [v for v in verification if not v.get("is_valid", False)]
    result["failed_count"] = len(failed_claims)
    result["failed_claim_ids"] = [v.get("claim_id") for v in failed_claims]

    if verbose:
        for v in verification:
            status = "PASS" if v.get("is_valid") else "FAIL"
            print(f"        {v.get('claim_id')}: {status} conf={v.get('confidence')} | {v.get('text', '')[:80]}")

    print(f"        → {len(verification)} verified, {len(failed_claims)} failed")

    # ── Step 3: Repair failed claims ──
    repaired_claims = []
    repair_count = 0

    for v in verification:
        if not v.get("is_valid", False):
            repair_count += 1
            print(f"    [3] Repairing {v.get('claim_id')}...", end=" ", flush=True)
            try:
                repaired_text = repair_claim(
                    problem=problem,
                    claim=v,
                    rationale=v.get("rationale", ""),
                )
                print("OK")
            except Exception as e:
                print(f"FAILED: {e}")
                repaired_text = v.get("text", "")

            repaired_claims.append({
                "claim_id": v.get("claim_id"),
                "text": repaired_text,
                "original_text": v.get("text"),
                "was_repaired": True,
            })
            if verbose:
                print(f"        Original: {v.get('text', '')[:100]}")
                print(f"        Repaired: {repaired_text[:100]}")
        else:
            repaired_claims.append({
                "claim_id": v.get("claim_id"),
                "text": v.get("text"),
                "original_text": v.get("text"),
                "was_repaired": False,
            })

    result["repaired_claims"] = repaired_claims
    result["repair_count"] = repair_count

    # ── Step 4: Reconstruct plan ──
    print("    [4] Reconstructing plan...", end=" ", flush=True)
    reconstructed_plan = "\n".join(
        c.get("text", "") for c in repaired_claims if c.get("text")
    )
    print("OK")
    result["reconstructed_plan"] = reconstructed_plan

    if verbose:
        print(f"        Plan: {reconstructed_plan[:200]}...")

    # ── Step 5: Run Agent B and C ──
    print("    [5] Running Agent B...", end=" ", flush=True)
    try:
        b_output = agent_b(problem, reconstructed_plan)
        print("OK")
    except Exception as e:
        print(f"FAILED: {e}")
        b_output = f"[Error: {e}]"
    result["agent_b"] = b_output

    print("    [6] Running Agent C...", end=" ", flush=True)
    try:
        c_output = agent_c(problem, reconstructed_plan, b_output)
        print("OK")
    except Exception as e:
        print(f"FAILED: {e}")
        c_output = f"[Error: {e}]"
    result["agent_c"] = c_output

    # ── Step 6: Evaluate ──
    print("    [7] Evaluating answer...", end=" ", flush=True)
    is_correct, prediction, gt = evaluate_answer(c_output, ground_truth)
    print(f"{'CORRECT' if is_correct else 'WRONG'} (pred={prediction}, gt={gt})")
    result["prediction"] = prediction
    result["correct"] = is_correct
    result["ground_truth_extracted"] = gt

    return result


def run_control_test(problem, correct_reasoning, ground_truth, verbose=False):
    """Run A3 pipeline on CORRECT reasoning (no error injected) as a control."""
    print("    [Control] No error injected — running same pipeline on correct reasoning")

    # Extract + verify only (no repair needed)
    try:
        claims = extract_claims(problem=problem, reasoning=correct_reasoning)
        verification = verify_claims(
            problem=problem, claims=claims, context=correct_reasoning, tau=0.80
        )
        failed = [v for v in verification if not v.get("is_valid", False)]
        print(f"    [Control] {len(claims)} claims, {len(failed)} failed (expected 0)")

        if verbose:
            for v in verification:
                status = "PASS" if v.get("is_valid") else "FAIL"
                print(f"        {v.get('claim_id')}: {status} conf={v.get('confidence')}")

        return {"claims": claims, "verification": verification, "failed_count": len(failed)}
    except Exception as e:
        print(f"    [Control] ERROR: {e}")
        return {"error": str(e)}


# ──────────────────────────────────────────────────────────────────────
# Auto-inject errors into real GSM8K problems
# ──────────────────────────────────────────────────────────────────────

def inject_arithmetic_error(reasoning: str) -> tuple[str, str]:
    """
    Auto-inject an error into reasoning text by changing a number.

    Finds the last number in the reasoning and offsets it by a small amount.
    Returns (corrupted_reasoning, description_of_error).
    """
    import re

    # Find all numbers in the reasoning
    numbers = re.findall(r'\b(\d+)\b', reasoning)
    if not numbers:
        return reasoning, "No numbers found to inject error"

    # Pick the last number (usually the final answer) and offset it
    target = numbers[-1]
    target_int = int(target)
    offset = 2 if target_int > 2 else 1
    corrupted = target_int + offset
    corrupted_str = str(corrupted)

    # Replace the last occurrence of the target number
    # Use rfind to get the last occurrence
    idx = reasoning.rfind(target)
    if idx == -1:
        return reasoning, "Could not find target number"

    corrupted_reasoning = reasoning[:idx] + corrupted_str + reasoning[idx + len(target):]
    description = f"Changed final number from {target} to {corrupted_str}"

    return corrupted_reasoning, description


# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Error injection test for A3 targeted repair")
    parser.add_argument("--use-gsm8k", type=int, default=0,
                        help="Also test on N real GSM8K problems with auto-injected errors")
    parser.add_argument("--verbose", action="store_true",
                        help="Show full claim and repair details")
    parser.add_argument("--output", type=str, default="results/error_injection_test.jsonl",
                        help="Output JSONL file for results")
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Clear previous results
    if output_path.exists():
        output_path.unlink()

    all_results = []

    # ── Part 1: Crafted test cases ──
    print("=" * 70)
    print("PART 1: CRAFTED ERROR INJECTION TEST CASES")
    print("=" * 70)

    for i, case in enumerate(CRAFTED_CASES):
        print(f"\n{'─' * 70}")
        print(f"Test {i+1}/{len(CRAFTED_CASES)}: {case['name']}")
        print(f"{'─' * 70}")
        print(f"  Problem: {case['problem'][:120]}...")
        print(f"  Error: {case['error_description']}")
        print(f"  Ground truth: {case['ground_truth']}")

        # Control test (no error)
        print(f"\n  ── CONTROL (correct reasoning, no error) ──")
        control = run_control_test(
            case["problem"], case["correct_reasoning"],
            case["ground_truth"], verbose=args.verbose
        )

        # Error injection test
        print(f"\n  ── ERROR INJECTION (corrupted reasoning) ──")
        result = run_a3_with_injected_error(
            case["problem"], case["corrupted_reasoning"],
            case["ground_truth"], verbose=args.verbose
        )

        result["test_name"] = case["name"]
        result["error_description"] = case["error_description"]
        result["control"] = control

        # Summary for this test
        print(f"\n  SUMMARY:")
        print(f"    Claims extracted: {len(result.get('claims_extracted', []))}")
        print(f"    Claims failed verification: {result.get('failed_count', 0)}")
        print(f"    Claims repaired: {result.get('repair_count', 0)}")
        print(f"    Final answer correct: {result.get('correct', False)}")
        print(f"    Prediction: {result.get('prediction')}")
        print(f"    Ground truth: {result.get('ground_truth_extracted')}")

        # Determine pipeline assessment
        caught = result.get("failed_count", 0) > 0
        repaired = result.get("repair_count", 0) > 0
        final_correct = result.get("correct", False)

        if not caught:
            assessment = "VERIFIER MISS — error NOT detected"
        elif not repaired:
            assessment = "VERIFIER CAUGHT — but no repair attempted (unexpected)"
        elif final_correct:
            assessment = "FULL SUCCESS — error detected, repaired, correct answer"
        else:
            assessment = "PARTIAL — error detected & repaired, but final answer still wrong"

        print(f"    Assessment: {assessment}")

        result["assessment"] = assessment

        # Save
        with open(output_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(result, ensure_ascii=False, default=str) + "\n")
        all_results.append(result)

    # ── Part 2: Real GSM8K with auto-injected errors ──
    if args.use_gsm8k > 0:
        print(f"\n\n{'=' * 70}")
        print(f"PART 2: REAL GSM8K PROBLEMS WITH AUTO-INJECTED ERRORS ({args.use_gsm8k} examples)")
        print("=" * 70)

        from datasets import load_dataset
        from agents.agent_a import agent_a

        dataset = load_dataset("openai/gsm8k", "main", split="test")

        for i in range(min(args.use_gsm8k, len(dataset))):
            item = dataset[i]
            problem = item["question"]
            ground_truth = item["answer"]

            print(f"\n{'─' * 70}")
            print(f"GSM8K Example {i+1}/{args.use_gsm8k}")
            print(f"{'─' * 70}")
            print(f"  Problem: {problem[:120]}...")

            # Get Agent A's (correct) reasoning
            print("  Getting Agent A reasoning...", end=" ", flush=True)
            try:
                correct_reasoning = agent_a(problem)
                print("OK")
            except Exception as e:
                print(f"FAILED: {e}")
                continue

            # Inject error
            corrupted_reasoning, error_desc = inject_arithmetic_error(correct_reasoning)
            print(f"  Injected error: {error_desc}")

            if args.verbose:
                print(f"  Original reasoning:\n{correct_reasoning[:300]}")
                print(f"  Corrupted reasoning:\n{corrupted_reasoning[:300]}")

            # Run A3 pipeline
            result = run_a3_with_injected_error(
                problem, corrupted_reasoning, ground_truth, verbose=args.verbose
            )
            result["test_name"] = f"GSM8K #{i}"
            result["error_description"] = error_desc
            result["original_agent_a"] = correct_reasoning

            caught = result.get("failed_count", 0) > 0
            repaired = result.get("repair_count", 0) > 0
            final_correct = result.get("correct", False)

            if not caught:
                assessment = "VERIFIER MISS — error NOT detected"
            elif not repaired:
                assessment = "VERIFIER CAUGHT — but no repair attempted"
            elif final_correct:
                assessment = "FULL SUCCESS — error detected, repaired, correct answer"
            else:
                assessment = "PARTIAL — error detected & repaired, but final answer wrong"

            print(f"\n  SUMMARY:")
            print(f"    Claims extracted: {len(result.get('claims_extracted', []))}")
            print(f"    Claims failed: {result.get('failed_count', 0)}")
            print(f"    Claims repaired: {result.get('repair_count', 0)}")
            print(f"    Final answer correct: {final_correct}")
            print(f"    Assessment: {assessment}")

            result["assessment"] = assessment

            with open(output_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(result, ensure_ascii=False, default=str) + "\n")
            all_results.append(result)

    # ── Final summary ──
    print(f"\n\n{'=' * 70}")
    print("OVERALL SUMMARY")
    print("=" * 70)

    total = len(all_results)
    verifier_misses = sum(1 for r in all_results if "VERIFIER MISS" in r.get("assessment", ""))
    full_success = sum(1 for r in all_results if "FULL SUCCESS" in r.get("assessment", ""))
    partial = sum(1 for r in all_results if "PARTIAL" in r.get("assessment", ""))

    print(f"  Total tests:          {total}")
    print(f"  Verifier misses:     {verifier_misses} (error not detected)")
    print(f"  Full success:        {full_success} (detected + repaired + correct)")
    print(f"  Partial success:     {partial} (detected + repaired, wrong answer)")
    print(f"  Verifier catch rate: {(total - verifier_misses) / total * 100:.1f}%" if total else "  N/A")
    print(f"  Repair success rate: {full_success / max(total - verifier_misses, 1) * 100:.1f}%" if (total - verifier_misses) > 0 else "  N/A")
    print(f"\n  Results saved to: {output_path}")


if __name__ == "__main__":
    main()
