#!/usr/bin/env python
"""Test A2 and A3 on a small sample."""

import sys
sys.path.insert(0, '.')

import json
from datasets import load_dataset
from evaluation.gsm8k_evaluator import evaluate_answer
from experiments.run_a2_full import run_a2_full
from experiments.run_a3_full import run_a3_full

# Test on first 5 examples
dataset = load_dataset("openai/gsm8k", "main", split="test")

print("COMPARATIVE TEST: A2 vs A3 (5 examples)")
print("=" * 60)

results = {"a2": 0, "a3": 0, "total": 0}

for i in range(5):
    item = dataset[i]
    problem = item["question"]
    ground_truth = item["answer"]
    
    print(f"\nExample {i + 1}/5:")
    print("-" * 60)
    
    # Run A2
    print("Running A2 (Full Regeneration)...", end=" ", flush=True)
    try:
        a2_result = run_a2_full(problem)
        a2_correct, a2_pred, _ = evaluate_answer(a2_result["agent_c"], ground_truth)
        print(f"Correct={a2_correct}")
        if a2_correct:
            results["a2"] += 1
    except Exception as e:
        print(f"Error: {str(e)[:50]}")
        a2_correct = False
    
    # Run A3
    print("Running A3 (Targeted Repair)...", end=" ", flush=True)
    try:
        a3_result = run_a3_full(problem)
        a3_correct, a3_pred, _ = evaluate_answer(a3_result["agent_c"], ground_truth)
        print(f"Correct={a3_correct}")
        if a3_correct:
            results["a3"] += 1
    except Exception as e:
        print(f"Error: {str(e)[:50]}")
        a3_correct = False
    
    results["total"] += 1
    
    # Summary
    print(f"Result: A2={a2_correct}, A3={a3_correct}")

print("\n" + "=" * 60)
print("Summary:")
print(f"A2: {results['a2']}/{results['total']} correct")
print(f"A3: {results['a3']}/{results['total']} correct")
print("Test Complete!")
