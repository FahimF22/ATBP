"""
Unified comparative experiment runner for ATBP.

Runs A0 (baseline), A2 (full regeneration), A3 (targeted repair),
and A4 (adaptive recovery) on the same GSM8K examples.

Usage:
    python run_comparative.py --num-examples=100 --strategies=a0,a2,a3,a4
"""

import sys
import argparse
import csv
import json
import time
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from datasets import load_dataset

from agents.agent_a import agent_a
from agents.agent_b import agent_b
from agents.agent_c import agent_c
from evaluation.gsm8k_evaluator import evaluate_answer
from logging_system.experiment_logger import save_experiment
from utils.metrics import aggregate_strategy_results

# Import strategy runners
from experiments.run_a2_full import run_a2_full
from experiments.run_a3_full import run_a3_full
from experiments.run_a4_full import run_a4_full


def run_a0_baseline(problem):
    """
    A0: Sequential baseline (no recovery).
    """

    start_time = time.time()

    try:
        plan = agent_a(problem)
    except Exception as e:
        plan = f"[Error in Agent A: {str(e)}]"

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
        "strategy": "a0_baseline",
        "problem": problem,
        "success": True,
        "agent_a": plan,
        "agent_b": b_output,
        "agent_c": c_output,
        "latency_seconds": latency,
    }


def run_all_strategies(problem, ground_truth, example_id, strategies):
    """
    Run specified strategies on the same problem.

    Returns: {
        "example_id": int,
        "problem": str,
        "ground_truth": str,
        "results": {
            "a0": {...},
            "a2": {...},
            "a3": {...},
            "a4": {...},
        }
    }
    """

    results = {
        "example_id": example_id,
        "problem": problem,
        "ground_truth": ground_truth,
        "results": {},
    }

    if "a0" in strategies:
        print(f"  Running A0...", end=" ", flush=True)
        try:
            a0_result = run_a0_baseline(problem)
            is_correct, prediction, gt = evaluate_answer(a0_result["agent_c"], ground_truth)
            a0_result["prediction"] = prediction
            a0_result["correct"] = is_correct
            results["results"]["a0"] = a0_result
            print(f"OK ({is_correct})")
        except Exception as e:
            print(f"FAIL (Connection Error: {type(e).__name__})")
            results["results"]["a0"] = {
                "strategy": "a0_baseline",
                "error": str(e),
                "skipped": True,
            }

    if "a2" in strategies:
        print(f"  Running A2...", end=" ", flush=True)
        try:
            a2_result = run_a2_full(problem)
            is_correct, prediction, gt = evaluate_answer(a2_result["agent_c"], ground_truth)
            a2_result["prediction"] = prediction
            a2_result["correct"] = is_correct
            results["results"]["a2"] = a2_result
            print(f"OK ({is_correct})")
        except Exception as e:
            print(f"FAIL (Connection Error: {type(e).__name__})")
            results["results"]["a2"] = {
                "strategy": "a2_full_regeneration",
                "error": str(e),
                "skipped": True,
            }

    if "a3" in strategies:
        print(f"  Running A3...", end=" ", flush=True)
        try:
            a3_result = run_a3_full(problem)
            is_correct, prediction, gt = evaluate_answer(a3_result["agent_c"], ground_truth)
            a3_result["prediction"] = prediction
            a3_result["correct"] = is_correct
            results["results"]["a3"] = a3_result
            print(f"OK ({is_correct})")
        except Exception as e:
            print(f"FAIL (Connection Error: {type(e).__name__})")
            results["results"]["a3"] = {
                "strategy": "a3_targeted_repair",
                "error": str(e),
                "skipped": True,
            }

    if "a4" in strategies:
        print(f"  Running A4...", end=" ", flush=True)
        try:
            a4_result = run_a4_full(problem)
            is_correct, prediction, gt = evaluate_answer(a4_result["agent_c"], ground_truth)
            a4_result["prediction"] = prediction
            a4_result["correct"] = is_correct
            results["results"]["a4"] = a4_result
            print(f"OK ({is_correct})")
        except Exception as e:
            print(f"FAIL (Connection Error: {type(e).__name__})")
            results["results"]["a4"] = {
                "strategy": "a4_adaptive_recovery",
                "error": str(e),
                "skipped": True,
            }

    return results


def generate_aggregate_csv(output_dir, strategies, results_by_strategy):
    """
    Generate aggregate comparison table.

    Each row: strategy, num_examples, correct, accuracy, mean_latency, ...
    """

    output_path = Path(output_dir) / "aggregate_comparison.csv"

    rows = []

    for strategy in strategies:
        if strategy not in results_by_strategy:
            continue

        records = results_by_strategy[strategy]
        agg = aggregate_strategy_results(strategy, records)

        row = {
            "strategy": strategy,
            "num_examples": agg["num_examples"],
            "correct": sum(1 for r in records if r.get("correct", False)),
            "accuracy": agg["accuracy"],
            "accuracy_percentage": agg["accuracy"] * 100,
            "mean_latency_seconds": agg["efficiency"]["mean_latency_seconds"],
            "median_latency_seconds": agg["efficiency"]["median_latency_seconds"],
            "total_latency_seconds": agg["efficiency"]["total_latency_seconds"],
            "error_cascade_rate": agg["error_cascade"]["ecr"],
            "error_cascade_rate_percentage": agg["error_cascade"]["ecr_percentage"],
            "repair_success_rate": agg["repair_success"]["rsr"],
            "repair_success_rate_percentage": agg["repair_success"]["rsr_percentage"],
            "collateral_damage_rate": agg["collateral_damage"]["cdr"],
            "collateral_damage_rate_percentage": agg["collateral_damage"]["cdr_percentage"],
            "mean_recovery_attempts": agg["recovery"]["mean_recovery_attempts"],
            "examples_needing_recovery": agg["recovery"]["examples_needing_recovery"],
        }

        rows.append(row)

    # Write CSV
    if rows:
        fieldnames = rows[0].keys()
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        print(f"\nAggregate results saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Run ATBP comparative experiment"
    )

    parser.add_argument(
        "--num-examples",
        type=int,
        default=5,
        help="Number of GSM8K examples to evaluate",
    )

    parser.add_argument(
        "--strategies",
        type=str,
        default="a0,a2,a3,a4",
        help="Comma-separated list of strategies to run",
    )

    parser.add_argument(
        "--output-dir",
        type=str,
        default="results",
        help="Output directory for results",
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility",
    )

    args = parser.parse_args()

    # Parse strategies
    strategies = [s.strip() for s in args.strategies.split(",")]

    # Ensure output directory exists
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load dataset
    print(f"Loading GSM8K dataset...")
    dataset = load_dataset("openai/gsm8k", "main", split="test")

    # Run experiments
    print(f"Running {args.num_examples} examples with strategies: {', '.join(strategies)}")
    print()

    results_by_strategy = {s: [] for s in strategies}

    for i in range(min(args.num_examples, len(dataset))):
        item = dataset[i]
        problem = item["question"]
        ground_truth = item["answer"]

        print(f"Example {i + 1}/{args.num_examples}")

        # Run all strategies on this problem
        comparison = run_all_strategies(problem, ground_truth, i, strategies)

        # Save individual results to per-strategy JSONL files
        for strategy in strategies:
            if strategy in comparison["results"]:
                record = {
                    "example_id": i,
                    "problem": problem,
                    "ground_truth": ground_truth,
                    **comparison["results"][strategy],
                }

                results_by_strategy[strategy].append(record)

                output_file = output_dir / f"{strategy}_results.jsonl"
                save_experiment(record, filename=str(output_file))

    # Generate aggregate comparison
    generate_aggregate_csv(output_dir, strategies, results_by_strategy)

    # Print summary
    print("\n" + "=" * 70)
    print("COMPARATIVE RESULTS SUMMARY")
    print("=" * 70)

    for strategy in strategies:
        records = results_by_strategy.get(strategy, [])
        if records:
            correct = sum(1 for r in records if r.get("correct", False))
            accuracy = correct / len(records) if records else 0.0
            mean_latency = (
                sum(r.get("latency_seconds", 0) for r in records) / len(records)
                if records
                else 0.0
            )

            print(
                f"{strategy.upper()}: "
                f"Accuracy={accuracy:.4f} ({correct}/{len(records)}) | "
                f"Mean Latency={mean_latency:.2f}s"
            )


if __name__ == "__main__":
    main()
