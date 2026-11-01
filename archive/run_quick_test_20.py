#!/usr/bin/env python
"""Quick 20-example test with Qwen2.5:7b - A0 vs A4 only"""

import sys
import io
sys.path.insert(0, '.')
# Force UTF-8 output on Windows to avoid cp1252 UnicodeEncodeError
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import time
from pathlib import Path
from datasets import load_dataset

from agents.agent_a import agent_a
from agents.agent_b import agent_b
from agents.agent_c import agent_c
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
    num_examples = 20
    output_dir = Path("results/quick_test_20")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Loading GSM8K dataset...")
    dataset = load_dataset("openai/gsm8k", "main", split="test")
    
    print(f"Running QUICK TEST: {num_examples} examples")
    print(f"Model: qwen2.5:7b")
    print(f"Strategies: A0, A4")
    print("=" * 80)
    
    results_a0 = []
    results_a4 = []
    
    for i in range(min(num_examples, len(dataset))):
        item = dataset[i]
        problem = item["question"]
        ground_truth = item["answer"]
        
        print(f"\n[{i+1:2d}/{num_examples}]", end=" ")
        
        # A0
        print("A0: ", end="", flush=True)
        try:
            a0_result = run_a0(problem)
            a0_correct, a0_pred, _ = evaluate_answer(a0_result.get("agent_c"), ground_truth)
            a0_result["correct"] = a0_correct
            a0_result["prediction"] = a0_pred
            a0_result["problem_id"] = i
            a0_result["ground_truth"] = ground_truth
            
            save_experiment(a0_result, filename=str(output_dir / "a0_baseline.jsonl"))
            results_a0.append(a0_result)
            
            print("OK" if a0_correct else "X", end=" | ")
        except Exception as e:
            print(f"X({str(e)[:20]})", end=" | ")
        
        # A4
        print("A4: ", end="", flush=True)
        try:
            a4_result = run_a4_full(problem)
            a4_correct, a4_pred, _ = evaluate_answer(a4_result.get("agent_c"), ground_truth)
            a4_result["correct"] = a4_correct
            a4_result["prediction"] = a4_pred
            a4_result["problem_id"] = i
            a4_result["ground_truth"] = ground_truth
            
            save_experiment(a4_result, filename=str(output_dir / "a4_adaptive_recovery.jsonl"))
            results_a4.append(a4_result)
            
            print("OK" if a4_correct else "X")
        except Exception as e:
            print(f"X({str(e)[:20]})")
    
    # Summary
    print("\n" + "=" * 80)
    print("QUICK TEST RESULTS")
    print("=" * 80)
    
    a0_correct = sum(1 for r in results_a0 if r.get("correct", False))
    a0_acc = a0_correct / len(results_a0) * 100 if results_a0 else 0
    
    a4_correct = sum(1 for r in results_a4 if r.get("correct", False))
    a4_acc = a4_correct / len(results_a4) * 100 if results_a4 else 0
    
    print(f"A0 Baseline:        {a0_acc:5.1f}% ({a0_correct:2d}/{len(results_a0)})")
    print(f"A4 Adaptive Recov:  {a4_acc:5.1f}% ({a4_correct:2d}/{len(results_a4)})")
    print(f"A4 improvement:     {a4_acc - a0_acc:+5.1f}pp")
    
    print(f"\nResults saved to: {output_dir}")


if __name__ == "__main__":
    main()
