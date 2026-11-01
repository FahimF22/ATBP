#!/usr/bin/env python
import sys
sys.path.insert(0, '.')
from experiments.run_a4_full import run_a4_full
from evaluation.gsm8k_evaluator import evaluate_answer
from datasets import load_dataset

ds = load_dataset('openai/gsm8k', 'main', split='test')
correct = 0
for i in range(3):
    try:
        r = run_a4_full(ds[i]['question'])
        answer = r.get('agent_c', '')
        ok, _, _ = evaluate_answer(answer, ds[i]['answer'])
        correct += int(ok)
        status = "PASS" if ok else "FAIL"
        print(f'Example {i+1}: {status} - Answer: {answer[:50]}...')
    except Exception as e:
        print(f'Example {i+1}: ERROR - {str(e)[:80]}...')
print(f'Accuracy: {correct}/3')
