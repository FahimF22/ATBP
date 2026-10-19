#!/usr/bin/env python
"""Debug A4 with verbose output"""

import sys
import io
sys.path.insert(0, '.')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from datasets import load_dataset
from experiments.run_a4_full import run_a4_full
from evaluation.gsm8k_evaluator import evaluate_answer

# Load first example
dataset = load_dataset("openai/gsm8k", "main", split="test")
problem = dataset[0]["question"]
ground_truth = dataset[0]["answer"]

print("="*80)
print("PROBLEM:")
print(problem)
print("\n" + "="*80)
print("Running A4...")
print("="*80 + "\n")

try:
    result = run_a4_full(problem)
    
    print("\n" + "="*80)
    print("RESULT STRUCTURE:")
    print("="*80)
    for key in sorted(result.keys()):
        value = result[key]
        if isinstance(value, str):
            if len(value) > 100:
                print(f"{key}: {value[:100]}...")
            else:
                print(f"{key}: {value}")
        else:
            print(f"{key}: {value}")
    
    print("\n" + "="*80)
    print("EVALUATION:")
    print("="*80)
    
    agent_c_output = result.get("agent_c")
    print(f"Agent C output: {agent_c_output}")
    print(f"\nGround truth: {ground_truth}")
    
    correct, pred, truth = evaluate_answer(agent_c_output, ground_truth)
    print(f"\nPrediction extracted: {pred}")
    print(f"Ground truth extracted: {truth}")
    print(f"Match: {correct}")
    
except Exception as e:
    print(f"\nEXCEPTION: {e}")
    import traceback
    traceback.print_exc()
