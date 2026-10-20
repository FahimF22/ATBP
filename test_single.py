#!/usr/bin/env python
import sys
import time
sys.path.insert(0, '.')
from experiments.run_a4_full import run_a4_full
from evaluation.gsm8k_evaluator import evaluate_answer
from datasets import load_dataset

ds = load_dataset('openai/gsm8k', 'main', split='test')
print("Testing single example...")
start = time.time()
try:
    r = run_a4_full(ds[0]['question'])
    answer = r.get('agent_c', '')
    ok, _, _ = evaluate_answer(answer, ds[0]['answer'])
    elapsed = time.time() - start
    status = "PASS" if ok else "FAIL"
    print(f'Result: {status}')
    print(f'Time: {elapsed:.1f}s')
    print(f'Answer: {answer[:80]}...')
except Exception as e:
    elapsed = time.time() - start
    print(f'ERROR after {elapsed:.1f}s: {str(e)[:100]}...')
