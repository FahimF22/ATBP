#!/usr/bin/env python
"""Debug A4 on a single example to see what's failing"""

import sys
import io
sys.path.insert(0, '.')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from datasets import load_dataset
from experiments.run_a4_full import run_a4_full
from evaluation.gsm8k_evaluator import evaluate_answer

# Load one example
dataset = load_dataset("openai/gsm8k", "main", split="test")
problem = dataset[0]["question"]
ground_truth = dataset[0]["answer"]

print("Problem:")
print(problem)
print("\nGround Truth:")
print(ground_truth)
print("\n" + "="*80)
print("Running A4...")
print("="*80 + "\n")

try:
    result = run_a4_full(problem)
    
    print("\nA4 Result:")
    print(f"Success: {result.get('success')}")
    print(f"Strategy: {result.get('strategy')}")
    
    if result.get('error'):
        print(f"Error: {result.get('error')}")
    
    if result.get('failure_reason'):
        print(f"Failure Reason: {result.get('failure_reason')}")
    
    print(f"\nAgent A output:\n{result.get('agent_a_original', 'N/A')[:200]}")
    print(f"\nAgent B output:\n{result.get('agent_b', 'N/A')[:200]}")
    print(f"\nAgent C output:\n{result.get('agent_c', 'N/A')[:200]}")
    
    # Evaluate
    correct, pred, _ = evaluate_answer(result.get("agent_c"), ground_truth)
    print(f"\nCorrect: {correct}")
    print(f"Prediction: {pred}")
    
except Exception as e:
    print(f"EXCEPTION: {e}")
    import traceback
    traceback.print_exc()
