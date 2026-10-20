import json

strategies = ['a0', 'a2', 'a3', 'a4']
results = {}

for strat in strategies:
    with open(f'results/evaluation_fixed/{strat}_results.jsonl', 'r') as f:
        lines = f.readlines()
        correct = 0
        for line in lines:
            data = json.loads(line)
            if data.get('correct', False):
                correct += 1
        accuracy = correct / len(lines) if lines else 0
        results[strat] = {'correct': correct, 'total': len(lines), 'accuracy': accuracy}
        
for strat in strategies:
    r = results[strat]
    pct = r['accuracy'] * 100
    print(f'{strat.upper()}: {r["correct"]}/{r["total"]} correct ({pct:.1f}%)')
