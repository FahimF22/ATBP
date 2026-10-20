#!/usr/bin/env python
"""
Focused test: Problem 7 (download timing) where A0 fails but A4 should recover.
This demonstrates recovery capability.
"""

import sys
import io
sys.path.insert(0, '.')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from datasets import load_dataset
from agents.agent_a import agent_a
from agents.agent_b import agent_b
from agents.agent_c import agent_c
from experiments.run_a4_full import run_a4_full
from evaluation.gsm8k_evaluator import evaluate_answer

# Load dataset
dataset = load_dataset("openai/gsm8k", "main", split="test")

# Problem 7 is the download timing problem where A0 fails
problem_indices = [7]  # Just test problem 7

print("="*80)
print("RECOVERY DEMONSTRATION TEST")
print("="*80)
print("\nTesting on problem that A0 gets WRONG:")
print("Problem 7: Download timing (A0 predicts 120, correct is 160)")
print("\n" + "="*80 + "\n")

for idx in problem_indices:
    item = dataset[idx]
    problem = item["question"]
    ground_truth = item["answer"]
    
    print(f"PROBLEM {idx}:")
    print(f"{problem}\n")
    
    # A0
    print("A0 (Baseline):")
    print("-" * 40)
    try:
        plan_a0 = agent_a(problem)
        b_a0 = agent_b(problem, plan_a0)
        c_a0 = agent_c(problem, plan_a0, b_a0)
        
        correct_a0, pred_a0, truth = evaluate_answer(c_a0, ground_truth)
        print(f"Agent A output: {plan_a0[:150]}...")
        print(f"\nPrediction: {pred_a0}")
        print(f"Correct: {correct_a0}")
        print(f"Expected: {truth}")
        if not correct_a0:
            print("❌ A0 WRONG")
        else:
            print("✓ A0 Correct")
    except Exception as e:
        print(f"ERROR: {str(e)[:100]}")
    
    # A4
    print("\n\nA4 (With Recovery):")
    print("-" * 40)
    try:
        a4_result = run_a4_full(problem)
        
        correct_a4, pred_a4, truth = evaluate_answer(a4_result.get("agent_c"), ground_truth)
        
        print(f"Recovery scope: {a4_result.get('recovery_scope')}")
        print(f"Claims extracted: {len(a4_result.get('claims_initial', []))}")
        print(f"Failed claims initially: {sum(1 for v in a4_result.get('verification_initial', []) if not v.get('is_valid'))}")
        
        if a4_result.get('regeneration_attempts') > 0:
            print(f"Regeneration attempts: {a4_result.get('regeneration_attempts')}")
        if a4_result.get('repair_attempts') > 0:
            print(f"Repair attempts: {a4_result.get('repair_attempts')}")
        
        print(f"\nAgent A original: {a4_result.get('agent_a_original', 'N/A')[:150]}...")
        if a4_result.get('agent_a_final') != a4_result.get('agent_a_original'):
            print(f"Agent A REGENERATED: {a4_result.get('agent_a_final', 'N/A')[:150]}...")
        
        print(f"\nPrediction: {pred_a4}")
        print(f"Correct: {correct_a4}")
        print(f"Expected: {truth}")
        
        if correct_a4:
            print("✓ A4 Correct")
        else:
            print("❌ A4 Wrong")
    except Exception as e:
        print(f"ERROR: {str(e)[:100]}")
    
    print("\n" + "="*80)
    print("COMPARISON:")
    print("="*80)
    print(f"A0: {'CORRECT' if correct_a0 else 'WRONG'}")
    print(f"A4: {'CORRECT' if correct_a4 else 'WRONG'}")
    
    if not correct_a0 and correct_a4:
        print("\n✓✓✓ SUCCESS: A4 RECOVERED FROM A0's MISTAKE ✓✓✓")
    elif correct_a0 and correct_a4:
        print("\n✓ Both correct (no recovery needed)")
    elif not correct_a0 and not correct_a4:
        print("\n✗✗ Both failed (recovery didn't help)")
    else:
        print("\n? A0 correct but A4 wrong (unexpected)")
