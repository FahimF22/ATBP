#!/usr/bin/env python
"""Test all 4 strategies: A0, A2, A3, A4"""

import sys
import io
sys.path.insert(0, '.')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import time
from pathlib import Path
from datasets import load_dataset

from agents.agent_a import agent_a
from agents.agent_b import agent_b
from agents.agent_c import agent_c
from experiments.run_a2_full import run_a2_full
from experiments.run_a3_full import run_a3_full
from experiments.run_a4_full import run_a4_full
from evaluation.gsm8k_evaluator import evaluate_answer
from logging_system.experiment_logger import save_experiment


def run_a0(problem):
    """A0: Sequential baseline."""
    start_time = time.time()
    try:
        plan = agent_a(problem)
        b_output = agent_b(problem, plan)
        c_output = agent_c(problem, plan, b_output)
        return {
            "strategy": "a0_baseline",
            "agent_a": plan,
            "agent_b": b_output,
            "agent_c": c_output,
            "latency_seconds": time.time() - start_time,
            "success": True,
        }
    except Exception as e:
        return {
            "strategy": "a0_baseline",
            "error": str(e)[:100],
            "success": False,
            "latency_seconds": time.time() - start_time,
        }


def main():
    num_examples = 10
    output_dir = Path("results/all_strategies_test")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Loading GSM8K dataset...")
    dataset = load_dataset("openai/gsm8k", "main", split="test")
    
    print(f"Testing {num_examples} examples with all 4 strategies")
    print("Strategies: A0, A2, A3, A4")
    print("=" * 80)
    
    results = {"a0": [], "a2": [], "a3": [], "a4": []}
    
    for i in range(min(num_examples, len(dataset))):
        item = dataset[i]
        problem = item["question"]
        ground_truth = item["answer"]
        
        print(f"\n[{i+1:2d}/{num_examples}] ", end="", flush=True)
        
        # A0
        print("A0:", end=" ", flush=True)
        try:
            a0_result = run_a0(problem)
            a0_correct, a0_pred, _ = evaluate_answer(a0_result.get("agent_c"), ground_truth)
            a0_result["correct"] = a0_correct
            a0_result["prediction"] = a0_pred
            a0_result["problem_id"] = i
            a0_result["ground_truth"] = ground_truth
            save_experiment(a0_result, filename=str(output_dir / "a0_baseline.jsonl"))
            results["a0"].append(a0_result)
            print("✓" if a0_correct else "✗", end=" ", flush=True)
        except Exception as e:
            print(f"E", end=" ", flush=True)
        
        # A2
        print("A2:", end=" ", flush=True)
        try:
            a2_result = run_a2_full(problem)
            a2_correct, a2_pred, _ = evaluate_answer(a2_result.get("agent_c"), ground_truth)
            a2_result["correct"] = a2_correct
            a2_result["prediction"] = a2_pred
            a2_result["problem_id"] = i
            a2_result["ground_truth"] = ground_truth
            save_experiment(a2_result, filename=str(output_dir / "a2_full_regeneration.jsonl"))
            results["a2"].append(a2_result)
            print("✓" if a2_correct else "✗", end=" ", flush=True)
        except Exception as e:
            print(f"E", end=" ", flush=True)
        
        # A3
        print("A3:", end=" ", flush=True)
        try:
            a3_result = run_a3_full(problem)
            a3_correct, a3_pred, _ = evaluate_answer(a3_result.get("agent_c"), ground_truth)
            a3_result["correct"] = a3_correct
            a3_result["prediction"] = a3_pred
            a3_result["problem_id"] = i
            a3_result["ground_truth"] = ground_truth
            save_experiment(a3_result, filename=str(output_dir / "a3_targeted_repair.jsonl"))
            results["a3"].append(a3_result)
            print("✓" if a3_correct else "✗", end=" ", flush=True)
        except Exception as e:
            print(f"E", end=" ", flush=True)
        
        # A4
        print("A4:", end=" ", flush=True)
        try:
            a4_result = run_a4_full(problem)
            a4_correct, a4_pred, _ = evaluate_answer(a4_result.get("agent_c"), ground_truth)
            a4_result["correct"] = a4_correct
            a4_result["prediction"] = a4_pred
            a4_result["problem_id"] = i
            a4_result["ground_truth"] = ground_truth
            save_experiment(a4_result, filename=str(output_dir / "a4_adaptive_recovery.jsonl"))
            results["a4"].append(a4_result)
            print("✓" if a4_correct else "✗", end=" ", flush=True)
        except Exception as e:
            print(f"E", end=" ", flush=True)
    
    # Summary
    print("\n\n" + "=" * 80)
    print("RESULTS SUMMARY")
    print("=" * 80)
    
    for strategy in ["a0", "a2", "a3", "a4"]:
        records = results[strategy]
        if records:
            correct = sum(1 for r in records if r.get("correct", False))
            accuracy = correct / len(records) * 100 if records else 0
            print(f"{strategy.upper():3s}: {accuracy:5.1f}% ({correct:2d}/{len(records):2d})")
    
    print(f"\nResults saved to: {output_dir}")


if __name__ == "__main__":
    main()
