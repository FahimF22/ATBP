#!/usr/bin/env python
import sys
import time
sys.path.insert(0, '.')

# Import config and modules
from experiments.run_a4_full import run_a4_full
from evaluation.gsm8k_evaluator import evaluate_answer
from datasets import load_dataset
import importlib

# Define combos
combos = [
    {"name": "Combo 1", "threshold": 0.75, "max_regen": 2},
    {"name": "Combo 2", "threshold": 0.80, "max_regen": 2},
    {"name": "Combo 3", "threshold": 0.75, "max_regen": 3},
    {"name": "Combo 4", "threshold": 0.70, "max_regen": 2},
]

results = {}

ds = load_dataset('openai/gsm8k', 'main', split='test')

for combo in combos:
    print(f"\n{'='*60}")
    print(f"Running {combo['name']}: threshold={combo['threshold']}, max_regen={combo['max_regen']}")
    print('='*60)
    
    # Update config
    from config import config
    config.VERIFICATION_THRESHOLD = combo['threshold']
    config.MAX_REGENERATIONS = combo['max_regen']
    # Reload to ensure new values are used
    importlib.reload(config)
    
    correct = 0
    start_time = time.time()
    
    for i in range(10):
        try:
            ex_start = time.time()
            r = run_a4_full(ds[i]['question'])
            answer = r.get('agent_c', '')
            ok, _, _ = evaluate_answer(answer, ds[i]['answer'])
            correct += int(ok)
            ex_time = time.time() - ex_start
            status = "PASS" if ok else "FAIL"
            print(f'  Ex {i+1}: {status} ({ex_time:.1f}s)')
        except Exception as e:
            print(f'  Ex {i+1}: ERROR - {str(e)[:60]}...')
    
    total_time = time.time() - start_time
    accuracy = correct / 10
    results[combo['name']] = {
        'accuracy': accuracy,
        'correct': correct,
        'time_seconds': total_time
    }
    print(f"\n{combo['name']} Result: {correct}/10 ({accuracy*100:.0f}%) in {total_time:.1f}s")

print(f"\n{'='*60}")
print("SUMMARY OF ALL COMBOS")
print('='*60)
for name, result in results.items():
    print(f"{name}: {result['correct']}/10 ({result['accuracy']*100:.0f}%) - {result['time_seconds']:.1f}s")

# Find best
best_combo = max(results.items(), key=lambda x: (x[1]['accuracy'], -x[1]['time_seconds']))
print(f"\n✓ BEST: {best_combo[0]} with {best_combo[1]['correct']}/10 accuracy")
