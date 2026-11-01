#!/usr/bin/env python
import sys
import signal
from contextlib import contextmanager

sys.path.insert(0, '.')
from experiments.run_a4_full import run_a4_full
from evaluation.gsm8k_evaluator import evaluate_answer
from datasets import load_dataset

class TimeoutException(Exception):
    pass

@contextmanager
def time_limit(seconds):
    def signal_handler(signum, frame):
        raise TimeoutException(f"Timed out after {seconds}s")
    signal.signal(signal.SIGALRM, signal_handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)

ds = load_dataset('openai/gsm8k', 'main', split='test')
correct = 0
completed = 0

for i in range(10):
    try:
        r = run_a4_full(ds[i]['question'])
        answer = r.get('agent_c', '')
        ok, _, _ = evaluate_answer(answer, ds[i]['answer'])
        correct += int(ok)
        completed += 1
        status = "PASS" if ok else "FAIL"
        print(f'Example {i+1}: {status} - Answer: {answer[:40]}...')
    except Exception as e:
        print(f'Example {i+1}: ERROR - {str(e)[:80]}...')

print(f'Accuracy: {correct}/{completed} ({correct*10//completed if completed > 0 else 0}/10 normalized)')
