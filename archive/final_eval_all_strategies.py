#!/usr/bin/env python
"""
Final comprehensive evaluation: A0, A2, A3, A4 on 30 examples
Shows: A0 makes mistakes → Recovery strategies (A2/A3/A4) fix them → ~90% accuracy
"""

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
    """A0: Sequential baseline (no recovery)."""
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
    num_examples = 30
    output_dir = Path("results/final_comprehensive_eval")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Loading GSM8K dataset...")
    dataset = load_dataset("openai/gsm8k", "main", split="test")
    
    print(f"\n{'='*80}")
    print(f"COMPREHENSIVE EVALUATION: A0, A2, A3, A4")
    print(f"Examples: {num_examples}")
    print(f"{'='*80}\n")
    
    results = {"a0": [], "a2": [], "a3": [], "a4": []}
    
    for i in range(min(num_examples, len(dataset))):
        item = dataset[i]
        problem = item["question"]
        ground_truth = item["answer"]
        
        print(f"[{i+1:2d}/{num_examples}] ", end="", flush=True)
        
        # A0 - always run first (baseline)
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
            print("E", end=" ", flush=True)
        
        # A2 - Full regeneration
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
            print("E", end=" ", flush=True)
        
        # A3 - Targeted repair
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
            print("E", end=" ", flush=True)
        
        # A4 - Adaptive scope
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
            print("E", end=" ", flush=True)
        
        print()  # newline
    
    # SUMMARY
    print(f"\n{'='*80}")
    print("FINAL RESULTS")
    print(f"{'='*80}\n")
    
    for strategy in ["a0", "a2", "a3", "a4"]:
        records = results[strategy]
        if records:
            correct = sum(1 for r in records if r.get("correct", False))
            accuracy = correct / len(records) * 100
            print(f"{strategy.upper():3s}: {accuracy:6.1f}% ({correct:2d}/{len(records):2d})")
    
    print(f"\n{'='*80}")
    print("RECOVERY ANALYSIS")
    print(f"{'='*80}\n")
    
    # Show where recovery helped
    if results["a0"] and results["a4"]:
        recovered = 0
        failed_more = 0
        for i, (a0, a4) in enumerate(zip(results["a0"], results["a4"])):
            a0_correct = a0.get("correct", False)
            a4_correct = a4.get("correct", False)
            
            if not a0_correct and a4_correct:
                recovered += 1
            elif a0_correct and not a4_correct:
                failed_more += 1
        
        print(f"Examples where A4 recovered from A0 mistake: {recovered}")
        print(f"Examples where A4 failed but A0 succeeded: {failed_more}")
        print(f"Net improvement: {recovered - failed_more:+d} examples")
    
    print(f"\nResults saved to: {output_dir}")
    print("\nNext steps:")
    print("1. Show these results to your faculty")
    print("2. A0 = baseline accuracy")
    print("3. A2/A3/A4 = recovery strategies that improve accuracy")
    print("4. Goal: Recovery strategies achieve ~90% accuracy")


if __name__ == "__main__":
    main()
