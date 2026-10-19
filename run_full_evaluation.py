#!/usr/bin/env python
"""
Run full 100-example evaluation on all strategies (A0, A2, A3, A4).

Usage:
    python run_full_evaluation.py [--num-examples=100] [--strategies=a0,a2,a3,a4]

This script:
1. Loads GSM8K test examples
2. Runs each strategy on each example
3. Saves results to JSONL files
4. Generates comparison summary
"""

import sys
sys.path.insert(0, '.')

import json
import time
import argparse
from pathlib import Path
from datasets import load_dataset
from concurrent.futures import ThreadPoolExecutor, TimeoutError

from agents.agent_a import agent_a
from agents.agent_b import agent_b
from agents.agent_c import agent_c
from experiments.run_a2_full import run_a2_full
from experiments.run_a3_full import run_a3_full
from experiments.run_a4_full import run_a4_full
from evaluation.gsm8k_evaluator import evaluate_answer
from logging_system.experiment_logger import save_experiment


def run_a0(problem):
    """A0: Sequential baseline (no recovery)."""
    start_time = time.time()
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            try:
                plan = executor.submit(agent_a, problem).result(timeout=180)
                b_output = executor.submit(agent_b, problem, plan).result(timeout=180)
                c_output = executor.submit(agent_c, problem, plan, b_output).result(timeout=180)
            except TimeoutError:
                return {
                    "strategy": "a0_baseline",
                    "correct": False,
                    "prediction": None,
                    "error": "timeout",
                    "latency_seconds": 180,
                    "success": False,
                }
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


def main():
    """Run full evaluation."""
    
    parser = argparse.ArgumentParser(
        description="Run full 100-example evaluation on all strategies"
    )
    parser.add_argument(
        "--num-examples",
        type=int,
        default=100,
        help="Number of examples to evaluate",
    )
    parser.add_argument(
        "--strategies",
        type=str,
        default="a0,a2,a3,a4",
        help="Comma-separated list of strategies",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="results",
        help="Output directory",
    )
    
    args = parser.parse_args()
    
    num_examples = args.num_examples
    strategies = [s.strip() for s in args.strategies.split(",")]
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Load dataset
    print(f"Loading GSM8K dataset...")
    dataset = load_dataset("openai/gsm8k", "main", split="test")
    
    print(f"Running evaluation on {num_examples} examples")
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
        if "a0" in strategies or any(s in strategies for s in ["a2", "a3", "a4"]):
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
                
                if "a0" in strategies:
                    save_experiment(
                        a0_result, 
                        filename=str(output_dir / "a0_baseline.jsonl")
                    )
                    results_by_strategy["a0"].append(a0_result)
                
                status = "✓" if a0_correct else "✗"
                print(f"{status}", end=" ", flush=True)
            except Exception as e:
                print(f"ERROR({str(e)[:15]})", end=" ", flush=True)
        
        # Run A2
        if "a2" in strategies:
            print("A2...", end=" ", flush=True)
            try:
                with ThreadPoolExecutor(max_workers=1) as executor:
                    try:
                        a2_result = executor.submit(run_a2_full, problem).result(timeout=180)
                    except TimeoutError:
                        a2_result = {
                            "strategy": "a2_full_regeneration",
                            "correct": False,
                            "prediction": None,
                            "error": "timeout",
                            "latency_seconds": 180,
                            "success": False,
                        }
                
                a2_correct, a2_pred, _ = evaluate_answer(
                    a2_result.get("agent_c"), ground_truth
                )
                a2_result["correct"] = a2_correct
                a2_result["prediction"] = a2_pred
                a2_result["problem_id"] = i
                a2_result["ground_truth"] = ground_truth
                
                save_experiment(
                    a2_result,
                    filename=str(output_dir / "a2_full_regeneration.jsonl")
                )
                results_by_strategy["a2"].append(a2_result)
                
                status = "✓" if a2_correct else "✗"
                print(f"{status}", end=" ", flush=True)
            except Exception as e:
                print(f"ERROR({str(e)[:15]})", end=" ", flush=True)
        
        # Run A3
        if "a3" in strategies:
            print("A3...", end=" ", flush=True)
            try:
                with ThreadPoolExecutor(max_workers=1) as executor:
                    try:
                        a3_result = executor.submit(run_a3_full, problem).result(timeout=180)
                    except TimeoutError:
                        a3_result = {
                            "strategy": "a3_targeted_repair",
                            "correct": False,
                            "prediction": None,
                            "error": "timeout",
                            "latency_seconds": 180,
                            "success": False,
                        }
                
                a3_correct, a3_pred, _ = evaluate_answer(
                    a3_result.get("agent_c"), ground_truth
                )
                a3_result["correct"] = a3_correct
                a3_result["prediction"] = a3_pred
                a3_result["problem_id"] = i
                a3_result["ground_truth"] = ground_truth
                
                save_experiment(
                    a3_result,
                    filename=str(output_dir / "a3_targeted_repair.jsonl")
                )
                results_by_strategy["a3"].append(a3_result)
                
                status = "✓" if a3_correct else "✗"
                print(f"{status}", end=" ", flush=True)
            except Exception as e:
                print(f"ERROR({str(e)[:15]})", end=" ", flush=True)
        
        # Run A4
        if "a4" in strategies:
            print("A4...", end=" ", flush=True)
            try:
                with ThreadPoolExecutor(max_workers=1) as executor:
                    try:
                        a4_result = executor.submit(run_a4_full, problem).result(timeout=180)
                    except TimeoutError:
                        a4_result = {
                            "strategy": "a4_adaptive_recovery",
                            "correct": False,
                            "prediction": None,
                            "error": "timeout",
                            "latency_seconds": 180,
                            "success": False,
                        }
                
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
    print("EVALUATION COMPLETE")
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
    for strategy in strategies:
        filename = output_dir / f"{strategy.replace('_', '_')}.jsonl"
        # Find actual file
        for f in output_dir.glob("*.jsonl"):
            if strategy.replace("_", "_") in f.name or strategy in f.name:
                print(f"  - {f}")
    
    print(f"\nOutput directory: {output_dir}")
    print("\nNext steps:")
    print("1. Review results in the output files")
    print("2. Run: python analyze_results.py")
    print("3. Compare strategies using metrics")


if __name__ == "__main__":
    main()
