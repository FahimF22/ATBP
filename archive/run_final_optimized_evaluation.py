#!/usr/bin/env python
"""
Final Optimized Evaluation with Qwen2.5:7b + All Fixes + Majority Voting

Strategies:
- A0: Baseline (simple chain)
- A0-MV: Baseline with majority voting (3 chains)
- A4: Adaptive recovery (with all bug fixes)

Dataset: GSM8K test set (100 examples)
Model: qwen2.5:7b
"""

import sys
sys.path.insert(0, '.')

import json
import time
from pathlib import Path
from datasets import load_dataset

from agents.agent_a import agent_a
from agents.agent_b import agent_b
from agents.agent_c import agent_c
from src.voting.majority_voting import majority_vote_solution
from experiments.run_a4_full import run_a4_full
from evaluation.gsm8k_evaluator import evaluate_answer
from logging_system.experiment_logger import save_experiment


def run_a0(problem):
    """A0: Sequential baseline (no recovery)."""
    start_time = time.time()
    try:
        plan = agent_a(problem)
        b_output = agent_b(problem, plan)
        c_output = agent_c(problem, plan, b_output)
        latency = time.time() - start_time
        
        return {
            "strategy": "a0_baseline",
            "agent_a": plan,
            "agent_b": b_output,
            "agent_c": c_output,
            "latency_seconds": latency,
            "success": True,
        }
    except Exception as e:
        return {
            "strategy": "a0_baseline",
            "error": str(e),
            "success": False,
            "latency_seconds": time.time() - start_time,
        }


def run_a0_majority_voting(problem, num_chains=3):
    """A0 with majority voting (3 independent chains)."""
    start_time = time.time()
    try:
        voting_result = majority_vote_solution(problem, num_chains=num_chains)
        latency = time.time() - start_time
        
        return {
            "strategy": "a0_majority_voting",
            "final_answer": voting_result["final_answer"],
            "all_answers": voting_result["all_answers"],
            "vote_counts": voting_result["vote_counts"],
            "num_chains": num_chains,
            "latency_seconds": latency,
            "success": voting_result["final_answer"] is not None,
        }
    except Exception as e:
        return {
            "strategy": "a0_majority_voting",
            "error": str(e),
            "success": False,
            "latency_seconds": time.time() - start_time,
        }


def main():
    """Run final evaluation with all optimizations."""
    
    num_examples = 100
    strategies = ["a0", "a0_mv", "a4"]
    output_dir = Path("results/evaluation_final_optimized")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Load dataset
    print(f"Loading GSM8K dataset...")
    dataset = load_dataset("openai/gsm8k", "main", split="test")
    
    print(f"Running final optimized evaluation on {num_examples} examples")
    print(f"Model: qwen2.5:7b")
    print(f"Strategies: {', '.join(strategies)}")
    print("=" * 80)
    
    # Results tracking
    results_by_strategy = {s: [] for s in strategies}
    
    # Run evaluation
    for i in range(min(num_examples, len(dataset))):
        item = dataset[i]
        problem = item["question"]
        ground_truth = item["answer"]
        
        print(f"\nExample {i + 1}/{num_examples}")
        print("-" * 80)
        
        # Run A0 (always first, used by others)
        if "a0" in strategies:
            print("  A0...", end=" ", flush=True)
            try:
                a0_result = run_a0(problem)
                a0_correct, a0_pred, _ = evaluate_answer(
                    a0_result.get("agent_c"), ground_truth
                )
                a0_result["correct"] = a0_correct
                a0_result["prediction"] = a0_pred
                a0_result["problem_id"] = i
                a0_result["ground_truth"] = ground_truth
                
                save_experiment(
                    a0_result, 
                    filename=str(output_dir / "a0_baseline.jsonl")
                )
                results_by_strategy["a0"].append(a0_result)
                
                status = "✓" if a0_correct else "✗"
                print(f"{status}", end=" ", flush=True)
            except Exception as e:
                print(f"ERROR({str(e)[:15]})", end=" ", flush=True)
        
        # Run A0 with Majority Voting
        if "a0_mv" in strategies:
            print("A0-MV...", end=" ", flush=True)
            try:
                a0_mv_result = run_a0_majority_voting(problem, num_chains=3)
                a0_mv_correct, a0_mv_pred, _ = evaluate_answer(
                    a0_mv_result.get("final_answer"), ground_truth
                )
                a0_mv_result["correct"] = a0_mv_correct
                a0_mv_result["prediction"] = a0_mv_pred
                a0_mv_result["problem_id"] = i
                a0_mv_result["ground_truth"] = ground_truth
                
                save_experiment(
                    a0_mv_result,
                    filename=str(output_dir / "a0_majority_voting.jsonl")
                )
                results_by_strategy["a0_mv"].append(a0_mv_result)
                
                status = "✓" if a0_mv_correct else "✗"
                print(f"{status}", end=" ", flush=True)
            except Exception as e:
                print(f"ERROR({str(e)[:15]})", end=" ", flush=True)
        
        # Run A4
        if "a4" in strategies:
            print("A4...", end=" ", flush=True)
            try:
                a4_result = run_a4_full(problem)
                a4_correct, a4_pred, _ = evaluate_answer(
                    a4_result.get("agent_c"), ground_truth
                )
                a4_result["correct"] = a4_correct
                a4_result["prediction"] = a4_pred
                a4_result["problem_id"] = i
                a4_result["ground_truth"] = ground_truth
                
                save_experiment(
                    a4_result,
                    filename=str(output_dir / "a4_adaptive_recovery.jsonl")
                )
                results_by_strategy["a4"].append(a4_result)
                
                status = "✓" if a4_correct else "✗"
                print(f"{status}", end=" ", flush=True)
            except Exception as e:
                print(f"ERROR({str(e)[:15]})", end=" ", flush=True)
        
        print()  # newline
    
    # Print summary
    print("\n" + "=" * 80)
    print("FINAL OPTIMIZED EVALUATION COMPLETE")
    print("=" * 80)
    
    print("\nResults Summary:")
    for strategy in strategies:
        records = results_by_strategy.get(strategy, [])
        if records:
            correct = sum(1 for r in records if r.get("correct", False))
            accuracy = correct / len(records) if records else 0
            print(
                f"{strategy:30s}: {accuracy*100:5.1f}% ({correct:3d}/{len(records):3d})"
            )
    
    print("\nResult Files:")
    for f in sorted(output_dir.glob("*.jsonl")):
        print(f"  - {f.name}")
    
    print(f"\nOutput directory: {output_dir}")
    print("\nConfiguration Used:")
    print("- Model: qwen2.5:7b")
    print("- Bug Fixes: Answer extraction (boxed/####/Answer: tags)")
    print("- Repair Logic: No number changes allowed")
    print("- A0-MV: 3-chain majority voting")
    print("\nNext steps:")
    print("1. Compare A0 vs A0-MV vs A4 accuracy improvements")
    print("2. When ready, switch to Claude Haiku for 90%+ baseline")


if __name__ == "__main__":
    main()
