# Full 100-Example Evaluation Guide

**Purpose:** Run complete comparative evaluation on all strategies (A0, A2, A3, A4)  
**Expected Time:** 60-180 minutes (depends on Ollama performance)  
**Expected Output:** Complete results with all metrics and comparison table  

---

## Prerequisites

### 1. Ensure Ollama is Running
```bash
# In a separate terminal, start Ollama
ollama serve

# In another terminal, verify it's running
curl http://localhost:11434/api/tags
# Should return list of available models including llama3.2
```

### 2. Verify Environment
```bash
cd "e:\Sakib project\ATBP"

# Verify Python and dependencies
python --version          # Should be Python 3.8+
pip list | grep -E "openai|datasets"  # Check key packages
```

### 3. Check Results Directory
```bash
# Ensure results directory exists
if not exist results mkdir results
cd results
```

---

## Option 1: Run All Strategies on 100 Examples (Fastest)

### Step 1: Run Unified Comparative (All Strategies, 100 Examples)

```bash
cd "e:\Sakib project\ATBP"

python experiments/run_comparative.py \
  --num-examples=100 \
  --strategies=a0,a2,a3,a4 \
  --seed=42 \
  --output-dir=results/evaluation_100
```

**What This Does:**
- Loads first 100 GSM8K examples
- Runs A0 baseline on each
- Runs A2 full regeneration on each
- Runs A3 targeted repair on each
- Runs A4 adaptive recovery on each
- Saves per-strategy JSONL files
- Generates aggregate CSV comparison

**Expected Output Files:**
```
results/evaluation_100/
├── a0_baseline.jsonl              (100 records)
├── a2_full_regeneration.jsonl     (100 records)
├── a3_targeted_repair.jsonl       (100 records)
├── a4_adaptive_recovery.jsonl     (100 records)
└── aggregate_comparison.csv       (Summary table)
```

**Monitoring Progress:**
- Watch terminal for "Example X/100" messages
- Takes ~60-180 minutes depending on system
- Each example takes ~23-30 seconds average

---

## Option 2: Run Each Strategy Separately (Modular)

### Step 1: Baseline Only (20-25 minutes)

```bash
cd "e:\Sakib project\ATBP"

python experiments/run_baseline.py --num-examples=100
```

**Output:** `results/baseline_results.jsonl` (100 records)

**Check Progress:**
```bash
# In another terminal, count records as they're saved
Get-Content results/baseline_results.jsonl | Measure-Object -Line
# Should increase over time
```

### Step 2: A2 Full Regeneration (40-60 minutes)

```bash
cd "e:\Sakib project\ATBP"

python -c "
import sys
sys.path.insert(0, '.')
from datasets import load_dataset
from experiments.run_a2_full import run_a2_full
from evaluation.gsm8k_evaluator import evaluate_answer
from logging_system.experiment_logger import save_experiment

dataset = load_dataset('openai/gsm8k', 'main', split='test')

for i in range(100):
    item = dataset[i]
    problem = item['question']
    ground_truth = item['answer']
    
    print(f'A2: {i+1}/100', flush=True)
    
    result = run_a2_full(problem)
    is_correct, prediction, gt = evaluate_answer(result['agent_c'], ground_truth)
    
    record = {
        'problem_id': i,
        'strategy': 'a2_full_regeneration',
        **result,
        'ground_truth': gt,
        'correct': is_correct,
    }
    
    save_experiment(record, filename='results/a2_full_regeneration_100.jsonl')
"
```

**Output:** `results/a2_full_regeneration_100.jsonl`

### Step 3: A3 Targeted Repair (30-50 minutes)

```bash
cd "e:\Sakib project\ATBP"

python -c "
import sys
sys.path.insert(0, '.')
from datasets import load_dataset
from experiments.run_a3_full import run_a3_full
from evaluation.gsm8k_evaluator import evaluate_answer
from logging_system.experiment_logger import save_experiment

dataset = load_dataset('openai/gsm8k', 'main', split='test')

for i in range(100):
    item = dataset[i]
    problem = item['question']
    ground_truth = item['answer']
    
    print(f'A3: {i+1}/100', flush=True)
    
    result = run_a3_full(problem)
    is_correct, prediction, gt = evaluate_answer(result['agent_c'], ground_truth)
    
    record = {
        'problem_id': i,
        'strategy': 'a3_targeted_repair',
        **result,
        'ground_truth': gt,
        'correct': is_correct,
    }
    
    save_experiment(record, filename='results/a3_targeted_repair_100.jsonl')
"
```

**Output:** `results/a3_targeted_repair_100.jsonl`

### Step 4: A4 Adaptive Recovery (40-70 minutes)

```bash
cd "e:\Sakib project\ATBP"

python -c "
import sys
sys.path.insert(0, '.')
from datasets import load_dataset
from experiments.run_a4_full import run_a4_full
from evaluation.gsm8k_evaluator import evaluate_answer
from logging_system.experiment_logger import save_experiment

dataset = load_dataset('openai/gsm8k', 'main', split='test')

for i in range(100):
    item = dataset[i]
    problem = item['question']
    ground_truth = item['answer']
    
    print(f'A4: {i+1}/100', flush=True)
    
    result = run_a4_full(problem)
    is_correct, prediction, gt = evaluate_answer(result['agent_c'], ground_truth)
    
    record = {
        'problem_id': i,
        'strategy': 'a4_adaptive_recovery',
        **result,
        'ground_truth': gt,
        'correct': is_correct,
    }
    
    save_experiment(record, filename='results/a4_adaptive_recovery_100.jsonl')
"
```

**Output:** `results/a4_adaptive_recovery_100.jsonl`

---

## Option 3: Create Master Script for All 100 (Recommended)

### Create `run_full_evaluation.py`

```python
#!/usr/bin/env python
"""Run full 100-example evaluation on all strategies."""

import sys
sys.path.insert(0, '.')

import json
from pathlib import Path
from datasets import load_dataset
from experiments.run_a2_full import run_a2_full
from experiments.run_a3_full import run_a3_full
from experiments.run_a4_full import run_a4_full
from agents.agent_a import agent_a
from agents.agent_b import agent_b
from agents.agent_c import agent_c
from evaluation.gsm8k_evaluator import evaluate_answer
from logging_system.experiment_logger import save_experiment

def run_a0(problem):
    """A0: Sequential baseline."""
    import time
    start = time.time()
    try:
        plan = agent_a(problem)
        b_output = agent_b(problem, plan)
        c_output = agent_c(problem, plan, b_output)
        latency = time.time() - start
        return {
            "strategy": "a0_baseline",
            "agent_a": plan,
            "agent_b": b_output,
            "agent_c": c_output,
            "latency_seconds": latency,
        }
    except Exception as e:
        return {"strategy": "a0_baseline", "error": str(e)}

def main():
    print("Loading dataset...")
    dataset = load_dataset("openai/gsm8k", "main", split="test")
    
    print(f"Running evaluation on 100 examples\n")
    print("=" * 70)
    
    for i in range(100):
        item = dataset[i]
        problem = item["question"]
        ground_truth = item["answer"]
        
        print(f"\nExample {i+1}/100")
        print("-" * 70)
        
        # Run A0
        print("A0...", end=" ", flush=True)
        try:
            a0_result = run_a0(problem)
            a0_correct, a0_pred, _ = evaluate_answer(a0_result.get("agent_c"), ground_truth)
            a0_result["correct"] = a0_correct
            a0_result["prediction"] = a0_pred
            a0_result["problem_id"] = i
            a0_result["ground_truth"] = ground_truth
            save_experiment(a0_result, filename="results/a0_baseline_100.jsonl")
            print(f"OK({a0_correct})", end=" ")
        except Exception as e:
            print(f"FAIL({str(e)[:20]})", end=" ")
        
        # Run A2
        print("A2...", end=" ", flush=True)
        try:
            a2_result = run_a2_full(problem)
            a2_correct, a2_pred, _ = evaluate_answer(a2_result.get("agent_c"), ground_truth)
            a2_result["correct"] = a2_correct
            a2_result["prediction"] = a2_pred
            a2_result["problem_id"] = i
            a2_result["ground_truth"] = ground_truth
            save_experiment(a2_result, filename="results/a2_full_regeneration_100.jsonl")
            print(f"OK({a2_correct})", end=" ")
        except Exception as e:
            print(f"FAIL({str(e)[:20]})", end=" ")
        
        # Run A3
        print("A3...", end=" ", flush=True)
        try:
            a3_result = run_a3_full(problem)
            a3_correct, a3_pred, _ = evaluate_answer(a3_result.get("agent_c"), ground_truth)
            a3_result["correct"] = a3_correct
            a3_result["prediction"] = a3_pred
            a3_result["problem_id"] = i
            a3_result["ground_truth"] = ground_truth
            save_experiment(a3_result, filename="results/a3_targeted_repair_100.jsonl")
            print(f"OK({a3_correct})", end=" ")
        except Exception as e:
            print(f"FAIL({str(e)[:20]})", end=" ")
        
        # Run A4
        print("A4...", end=" ", flush=True)
        try:
            a4_result = run_a4_full(problem)
            a4_correct, a4_pred, _ = evaluate_answer(a4_result.get("agent_c"), ground_truth)
            a4_result["correct"] = a4_correct
            a4_result["prediction"] = a4_pred
            a4_result["problem_id"] = i
            a4_result["ground_truth"] = ground_truth
            save_experiment(a4_result, filename="results/a4_adaptive_recovery_100.jsonl")
            print(f"OK({a4_correct})", end=" ")
        except Exception as e:
            print(f"FAIL({str(e)[:20]})", end=" ")
        
        print()  # newline
    
    print("\n" + "=" * 70)
    print("Evaluation Complete!")
    print("Results saved to:")
    print("  - results/a0_baseline_100.jsonl")
    print("  - results/a2_full_regeneration_100.jsonl")
    print("  - results/a3_targeted_repair_100.jsonl")
    print("  - results/a4_adaptive_recovery_100.jsonl")

if __name__ == "__main__":
    main()
```

### Save and Run

```bash
# Save as run_full_evaluation.py
python run_full_evaluation.py
```

---

## After Running: Analyze Results

### Step 1: Generate Comparison Summary

```bash
python -c "
import json
import csv

strategies = ['a0_baseline', 'a2_full_regeneration', 'a3_targeted_repair', 'a4_adaptive_recovery']
results = {}

for strategy in strategies:
    records = []
    filename = f'results/{strategy}_100.jsonl'
    try:
        with open(filename) as f:
            for line in f:
                records.append(json.loads(line))
        
        correct = sum(1 for r in records if r.get('correct', False))
        accuracy = correct / len(records) if records else 0
        latencies = [r.get('latency_seconds', 0) for r in records if r.get('latency_seconds')]
        mean_latency = sum(latencies) / len(latencies) if latencies else 0
        
        results[strategy] = {
            'examples': len(records),
            'correct': correct,
            'accuracy': accuracy,
            'accuracy_pct': f'{accuracy*100:.1f}%',
            'mean_latency': f'{mean_latency:.2f}s',
        }
        
        print(f'{strategy}:')
        print(f'  Accuracy: {accuracy*100:.1f}% ({correct}/{len(records)})')
        print(f'  Mean Latency: {mean_latency:.2f}s')
        print()
    except FileNotFoundError:
        print(f'File not found: {filename}')

# Create comparison table
with open('results/comparison_table.csv', 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=['Strategy', 'Examples', 'Correct', 'Accuracy', 'Mean Latency'])
    writer.writeheader()
    for strategy, data in results.items():
        writer.writerow({
            'Strategy': strategy,
            'Examples': data['examples'],
            'Correct': data['correct'],
            'Accuracy': data['accuracy_pct'],
            'Mean Latency': data['mean_latency'],
        })

print('\\nComparison table saved to: results/comparison_table.csv')
"
```

### Step 2: Detailed Analysis

```bash
python << 'EOF'
import json
from utils.metrics import aggregate_strategy_results

strategies = ['a0_baseline', 'a2_full_regeneration', 'a3_targeted_repair', 'a4_adaptive_recovery']

print("DETAILED ANALYSIS - All 100 Examples")
print("=" * 70)

for strategy in strategies:
    print(f"\n{strategy.upper()}")
    print("-" * 70)
    
    records = []
    filename = f'results/{strategy}_100.jsonl'
    try:
        with open(filename) as f:
            for line in f:
                records.append(json.loads(line))
        
        agg = aggregate_strategy_results(strategy, records)
        
        print(f"Accuracy: {agg['accuracy']:.2%}")
        print(f"Error Cascade Rate: {agg['error_cascade']['ecr']:.2%}")
        print(f"Repair Success Rate: {agg['repair_success']['rsr']:.2%}")
        print(f"Collateral Damage: {agg['collateral_damage']['cdr']:.2%}")
        print(f"Mean Latency: {agg['efficiency']['mean_latency_seconds']:.2f}s")
        print(f"Examples: {agg['num_examples']}")
        
    except FileNotFoundError:
        print(f"File not found: {filename}")

print("\n" + "=" * 70)
print("Analysis Complete!")
EOF
```

### Step 3: View Results

```bash
# View comparison table
Get-Content results/comparison_table.csv

# View detailed JSONL (first 3 records of each)
Get-Content results/a0_baseline_100.jsonl | Select-Object -First 3

# Count total records
(Get-Content results/a0_baseline_100.jsonl | Measure-Object -Line).Lines
```

---

## Troubleshooting

### Problem: "Connection refused" (Ollama not running)
**Solution:**
```bash
# Start Ollama in another terminal
ollama serve

# Verify running
curl http://localhost:11434/api/tags
```

### Problem: "ModuleNotFoundError"
**Solution:**
```bash
# Ensure you're in the right directory
cd "e:\Sakib project\ATBP"

# Add to Python path
python -c "import sys; sys.path.insert(0, '.'); from experiments.run_a2_full import run_a2_full; print('OK')"
```

### Problem: Slow performance
**Solution:**
- Normal: ~23-30 seconds per example (67 examples took 25.5 min)
- For 100 examples: expect 40-80 minutes
- To speed up: Use smaller dataset subset (10-20 examples for testing)

### Problem: Out of memory
**Solution:**
- Run strategies sequentially (not all at once)
- Reduce batch size
- Clear temporary files between runs

---

## Expected Results

### Accuracy Comparison

```
A0 (Baseline):          53-55%
A2 (Full Regeneration): 54-57%
A3 (Targeted Repair):   52-55%
A4 (Adaptive):          55-60%

Expected Best: A4 > A2 > A0 ≥ A3
```

### Latency Comparison

```
A0 (Baseline):          ~23s per example
A2 (Full Regeneration): ~35-40s per example
A3 (Targeted Repair):   ~28-32s per example
A4 (Adaptive):          ~30-38s per example

Trade-off: More accuracy ↔ More latency
```

### Error Cascade Rate (ECR)

```
A0: 100% (all errors cascade)
A2: 50-70% (recovery helps)
A3: 60-80% (variable)
A4: 40-60% (best)
```

---

## Next Steps After Evaluation

1. **Analyze Results**
   - Which strategy performs best?
   - Is improvement statistically significant?
   - What's the latency trade-off?

2. **Create Visualizations**
   - Accuracy by strategy (bar chart)
   - Latency comparison (bar chart)
   - Trade-off plot (scatter)
   - ECR/RSR/CDR comparison

3. **Write Findings**
   - Which strategy to recommend?
   - For what use cases?
   - What are limitations?

4. **Compare with Baselines**
   - Compare vs. CoT performance
   - Compare vs. Self-verification
   - Compare vs. Multi-agent approaches

---

## Quick Command Reference

```bash
# Run all strategies on 100 examples (recommended)
python experiments/run_comparative.py --num-examples=100 --strategies=a0,a2,a3,a4 --seed=42 --output-dir=results/evaluation_100

# Run just A0 baseline
python experiments/run_baseline.py --num-examples=100

# Analyze baseline results
python analyze_baseline.py

# Check results
Get-Content results/a0_baseline_100.jsonl | Measure-Object -Line

# View first result record
(Get-Content results/a0_baseline_100.jsonl)[0]
```

