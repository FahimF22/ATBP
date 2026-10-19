#!/usr/bin/env python
import sys
sys.path.insert(0, '.')
from experiments.run_a4_full import run_a4_full
from datasets import load_dataset
from evaluation.gsm8k_evaluator import evaluate_answer

ds = load_dataset('openai/gsm8k', 'main', split='test')
correct = 0

for i in range(5):
    r = run_a4_full(ds[i]['question'])
    ok, _, _ = evaluate_answer(r.get('agent_c'), ds[i]['answer'])
    correct += int(ok)
    print(f'Ex {i+1}: {ok} scope={r.get("recovery_scope")}')

print(f'Smoke: {correct}/5')
