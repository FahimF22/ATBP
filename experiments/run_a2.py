import json
import time
from pathlib import Path

from agents.agent_a import agent_a
from src.verification.claim_extractor import extract_claims
from src.verification.claim_verifier import verify_claims


MAX_REGENERATIONS = 3
VERIFICATION_THRESHOLD = 0.80


def run_a2(problem):
    """
    A2: Verification + Full Regeneration.

    If any atomic claim in Agent A's output fails verification,
    the entire Agent A output is discarded and regenerated.
    """

    total_attempts = 0
    total_failed_claims = 0
    start_time = time.perf_counter()

    for attempt in range(MAX_REGENERATIONS + 1):

        total_attempts += 1

        # ---------------------------------------------------------
        # 1. Generate a complete Agent A plan
        # ---------------------------------------------------------
        plan = agent_a(problem)

        # ---------------------------------------------------------
        # 2. Extract atomic claims
        # ---------------------------------------------------------
        claims = extract_claims(
            problem=problem,
            reasoning=plan,
        )

        if not claims:
            print("WARNING: No claims were extracted.")
            continue

        # ---------------------------------------------------------
        # 3. Verify every claim
        # ---------------------------------------------------------
        verification_results = verify_claims(
            problem=problem,
            claims=claims,
            context=plan,
            tau=VERIFICATION_THRESHOLD,
        )

        failed_claims = [
            result
            for result in verification_results
            if not result.get("is_valid", False)
        ]

        total_failed_claims += len(failed_claims)

        # ---------------------------------------------------------
        # 4. If everything is valid, accept the COMPLETE plan
        # ---------------------------------------------------------
        if not failed_claims:

            latency = time.perf_counter() - start_time

            return {
                "problem": problem,
                "final_plan": plan,
                "claims": claims,
                "verification": verification_results,
                "accepted": True,
                "regenerations": attempt,
                "attempts": total_attempts,
                "failed_claims": total_failed_claims,
                "latency_seconds": latency,
            }

        # ---------------------------------------------------------
        # 5. Otherwise discard the ENTIRE plan.
        # ---------------------------------------------------------
        print(
            f"A2: attempt {attempt + 1} failed "
            f"with {len(failed_claims)} invalid claim(s)."
        )

        if attempt < MAX_REGENERATIONS:
            print("A2: discarding entire Agent A output.")
            print("A2: regenerating Agent A plan...")

    # -------------------------------------------------------------
    # All attempts failed
    # -------------------------------------------------------------

    latency = time.perf_counter() - start_time

    return {
        "problem": problem,
        "final_plan": None,
        "claims": [],
        "verification": [],
        "accepted": False,
        "regenerations": MAX_REGENERATIONS,
        "attempts": total_attempts,
        "failed_claims": total_failed_claims,
        "latency_seconds": latency,
    }


def main():

    # -------------------------------------------------------------
    # Small test problem
    # -------------------------------------------------------------

    problem = (
        "A shop has 5 apples. Each apple costs $2. "
        "What is the total cost?"
    )

    print("=" * 70)
    print("A2: VERIFY + FULL REGENERATION")
    print("=" * 70)

    result = run_a2(problem)

    print("\nRESULT")
    print("-" * 70)

    print("Accepted:", result["accepted"])
    print("Attempts:", result["attempts"])
    print("Regenerations:", result["regenerations"])
    print("Failed claims:", result["failed_claims"])
    print("Latency:", round(result["latency_seconds"], 3), "seconds")

    print("\nFINAL AGENT A PLAN")
    print("-" * 70)

    if result["final_plan"]:
        print(result["final_plan"])
    else:
        print("No valid plan produced.")

    print("\nVERIFICATION")
    print("-" * 70)

    for item in result["verification"]:
        print(json.dumps(item, indent=2))


if __name__ == "__main__":
    main()