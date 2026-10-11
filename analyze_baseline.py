#!/usr/bin/env python
"""Analyze baseline results."""

import json
import sys

sys.path.insert(0, '.')

# Read baseline results
records = []
with open('results/baseline_results.jsonl') as f:
    for line in f:
        records.append(json.loads(line))

correct = sum(1 for r in records if r['correct'])
total = len(records)
accuracy = correct / total if total > 0 else 0

print('BASELINE (A0) RESULTS')
print('=' * 60)
print(f'Examples: {total}')
print(f'Correct: {correct}')
print(f'Accuracy: {accuracy:.2%}')

# Show per-example results
print('\nPer-Example Results:')
print('-' * 60)
for i, r in enumerate(records):
    status = 'OK' if r['correct'] else 'FAIL'
    print(f'{i}: {status} | Pred: {r["prediction"]:>6} | Truth: {r["ground_truth"]:>6}')

# Calculate mean latency
latencies = [r['latency_seconds'] for r in records]
mean_latency = sum(latencies) / len(latencies) if latencies else 0
print('\nPerformance:')
print(f'Mean Latency: {mean_latency:.2f} seconds')
print(f'Min Latency:  {min(latencies):.2f} seconds')
print(f'Max Latency:  {max(latencies):.2f} seconds')
print(f'Total Time:   {sum(latencies):.2f} seconds')

print('\n' + '=' * 60)
print('Analysis Summary:')
print('=' * 60)
if accuracy >= 0.5:
    print(f'✅ Good baseline: {accuracy:.1%} accuracy')
elif accuracy >= 0.3:
    print(f'⚠️  Moderate baseline: {accuracy:.1%} accuracy')
else:
    print(f'⚠️  Low baseline: {accuracy:.1%} accuracy')
    print('   (Recovery strategies should help improve this)')
