"""
Metrics calculation for ATBP experimental evaluation.

Implements:
- Accuracy
- Error Cascade Rate (ECR)
- Repair Success Rate (RSR)
- Collateral Damage Rate (CDR)
- Token efficiency
- Latency efficiency
"""

from collections import defaultdict
from typing import List, Dict, Any


def calculate_accuracy(records: List[Dict[str, Any]]) -> float:
    """
    Calculate accuracy: correct_count / total_count
    """
    if not records:
        return 0.0

    correct = sum(1 for r in records if r.get("correct", False))
    return correct / len(records)


def calculate_error_cascade_rate(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Error Cascade Rate: percentage of failed upstream claims that propagate downstream.

    For each record:
    - Identify claims that failed verification (is_valid=False)
    - Check if the final answer is incorrect
    - If final answer is wrong and verification detected failures: cascade occurred
    - If final answer is correct despite failures: repair or correction happened
    - If final answer is wrong but verification found no failures: downstream error

    Returns: {
        "total_examples": N,
        "failed_claim_examples": M (examples where verification detected failures),
        "cascaded_to_final": K (examples where failures led to wrong answer),
        "ecr": K / M if M > 0 else 0.0,
        "description": human-readable summary
    }
    """

    total = len(records)
    failed_claim_examples = 0
    cascaded_to_final = 0

    for record in records:
        verification = record.get("verification", [])

        # Check if any claims failed verification
        has_failed_claims = any(
            not v.get("is_valid", False) for v in verification
        )

        if has_failed_claims:
            failed_claim_examples += 1

            # If final answer is also wrong, cascade occurred
            if not record.get("correct", False):
                cascaded_to_final += 1

    if failed_claim_examples == 0:
        ecr = 0.0
    else:
        ecr = cascaded_to_final / failed_claim_examples

    return {
        "total_examples": total,
        "examples_with_failed_claims": failed_claim_examples,
        "examples_with_cascaded_errors": cascaded_to_final,
        "ecr": ecr,
        "ecr_percentage": ecr * 100,
    }


def calculate_repair_success_rate(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Repair Success Rate: successful repairs / total repair attempts.

    A repair is successful if:
    - A claim was repaired (was_repaired=True in claims_repaired)
    - Post-repair verification shows is_valid=True for that claim

    Returns: {
        "total_repair_attempts": N,
        "successful_repairs": M,
        "rsr": M / N if N > 0 else 0.0,
        "description": human-readable summary
    }
    """

    total_repairs = 0
    successful = 0

    for record in records:
        repaired_claims = record.get("claims_repaired", [])
        verification_after = record.get("verification_after", [])

        for claim in repaired_claims:
            if claim.get("was_repaired", False):
                total_repairs += 1

                # Check if post-repair verification shows it's valid
                for v in verification_after:
                    if v.get("claim_id") == claim.get("claim_id"):
                        if v.get("is_valid", False):
                            successful += 1
                        break

    if total_repairs == 0:
        rsr = 0.0
    else:
        rsr = successful / total_repairs

    return {
        "total_repair_attempts": total_repairs,
        "successful_repairs": successful,
        "rsr": rsr,
        "rsr_percentage": rsr * 100,
    }


def calculate_collateral_damage_rate(
    records: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Collateral Damage Rate: previously valid claims that become invalid after repair.

    For each record:
    - Identify claims that were NOT repaired but were valid before
    - Check if they are still valid after repair
    - If valid before but invalid after: collateral damage occurred

    Returns: {
        "originally_valid_claims": N,
        "damaged_claims": M,
        "cdr": M / N if N > 0 else 0.0,
        "description": human-readable summary
    }
    """

    original_valid = 0
    damaged = 0

    for record in records:
        repaired_claims = record.get("claims_repaired", [])
        verification_before = record.get("verification_before", [])
        verification_after = record.get("verification_after", [])

        # Map claim IDs to before/after validity
        before_validity = {
            v.get("claim_id"): v.get("is_valid", False)
            for v in verification_before
        }
        after_validity = {
            v.get("claim_id"): v.get("is_valid", False)
            for v in verification_after
        }

        for claim in repaired_claims:
            claim_id = claim.get("claim_id")
            was_repaired = claim.get("was_repaired", False)

            if not was_repaired:
                # This claim was not repaired; check for collateral damage
                if before_validity.get(claim_id, False):
                    original_valid += 1

                    if not after_validity.get(claim_id, False):
                        damaged += 1

    if original_valid == 0:
        cdr = 0.0
    else:
        cdr = damaged / original_valid

    return {
        "originally_valid_claims": original_valid,
        "damaged_claims": damaged,
        "cdr": cdr,
        "cdr_percentage": cdr * 100,
    }


def calculate_efficiency_metrics(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calculate token and latency efficiency.

    Returns: {
        "mean_latency_seconds": float,
        "median_latency_seconds": float,
        "mean_tokens": float,
        "median_tokens": float,
        "total_tokens": int,
        "total_latency_seconds": float,
        "examples_with_tokens": int,
    }
    """

    latencies = []
    tokens_list = []

    for record in records:
        latency = record.get("latency_seconds", 0)
        if latency:
            latencies.append(latency)

        # Count tokens if available (from LLM responses)
        # This is a placeholder; actual token counting would require
        # modifying agents to return token counts
        tokens = record.get("tokens_used", 0)
        if tokens:
            tokens_list.append(tokens)

    # Calculate statistics
    if latencies:
        latencies.sort()
        mean_latency = sum(latencies) / len(latencies)
        median_latency = (
            latencies[len(latencies) // 2]
            if len(latencies) % 2 == 1
            else (
                latencies[len(latencies) // 2 - 1]
                + latencies[len(latencies) // 2]
            )
            / 2
        )
    else:
        mean_latency = 0.0
        median_latency = 0.0

    if tokens_list:
        tokens_list.sort()
        mean_tokens = sum(tokens_list) / len(tokens_list)
        median_tokens = (
            tokens_list[len(tokens_list) // 2]
            if len(tokens_list) % 2 == 1
            else (
                tokens_list[len(tokens_list) // 2 - 1]
                + tokens_list[len(tokens_list) // 2]
            )
            / 2
        )
        total_tokens = sum(tokens_list)
    else:
        mean_tokens = 0.0
        median_tokens = 0.0
        total_tokens = 0

    return {
        "mean_latency_seconds": mean_latency,
        "median_latency_seconds": median_latency,
        "mean_tokens": mean_tokens,
        "median_tokens": median_tokens,
        "total_tokens": total_tokens,
        "total_latency_seconds": sum(latencies),
        "examples_with_latency": len(latencies),
        "examples_with_tokens": len(tokens_list),
    }


def calculate_recovery_statistics(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calculate recovery-specific statistics.

    Returns: {
        "examples_with_recovery": N,
        "mean_recovery_attempts": float,
        "max_recovery_attempts": int,
        "recovery_success_rate": float,
        "examples_needing_recovery": N,
    }
    """

    recovery_attempts = []
    examples_with_recovery = 0
    examples_needing_recovery = 0
    successful_recoveries = 0

    for record in records:
        # Check for regeneration attempts (A2)
        regen = record.get("regeneration_attempts", 0)
        if regen > 0:
            recovery_attempts.append(regen)
            examples_with_recovery += 1
            if record.get("correct", False):
                successful_recoveries += 1
            examples_needing_recovery += 1

        # Check for repair attempts (A3)
        repairs = record.get("repair_attempts", 0)
        if repairs > 0:
            recovery_attempts.append(repairs)
            examples_with_recovery += 1
            if record.get("correct", False):
                successful_recoveries += 1
            if regen == 0:  # Count only if not already counted as regen
                examples_needing_recovery += 1

    if recovery_attempts:
        mean_attempts = sum(recovery_attempts) / len(recovery_attempts)
        max_attempts = max(recovery_attempts)
    else:
        mean_attempts = 0.0
        max_attempts = 0

    if examples_needing_recovery > 0:
        recovery_success = successful_recoveries / examples_needing_recovery
    else:
        recovery_success = 0.0

    return {
        "examples_with_recovery": examples_with_recovery,
        "examples_needing_recovery": examples_needing_recovery,
        "mean_recovery_attempts": mean_attempts,
        "max_recovery_attempts": max_attempts,
        "recovery_success_rate": recovery_success,
        "recovery_success_rate_percentage": recovery_success * 100,
    }


def aggregate_strategy_results(
    strategy_name: str, records: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Aggregate all metrics for a single strategy.
    """

    return {
        "strategy": strategy_name,
        "num_examples": len(records),
        "accuracy": calculate_accuracy(records),
        "error_cascade": calculate_error_cascade_rate(records),
        "repair_success": calculate_repair_success_rate(records),
        "collateral_damage": calculate_collateral_damage_rate(records),
        "efficiency": calculate_efficiency_metrics(records),
        "recovery": calculate_recovery_statistics(records),
    }
