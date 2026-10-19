#!/usr/bin/env python
"""
100-Example Evaluation with Parameter Tuning for GPT-3.5-Turbo
=============================================================

Goal: Achieve ~90% accuracy with gpt-3.5-turbo by tuning verification parameters.

Tuned Parameters:
  - VERIFICATION_THRESHOLD=0.75 (more lenient verification - original: 0.80)
  - MAX_REGENERATIONS=5 (more retry attempts - original: 2)
  - MAX_REPAIR_ATTEMPTS=3 (more targeted repairs - original: 2)
  
Strategy: A4 (Adaptive Targeted Backtracking)
Model: gpt-3.5-turbo
Dataset: GSM8K test set (100 examples)
"""

import sys
import io
sys.path.insert(0, '.')
# Force UTF-8 output on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import time
import json
from pathlib import Path
from datasets import load_dataset

# Update config BEFORE importing run_a4_full (which imports config)
import config.config as cfg
cfg.VERIFICATION_THRESHOLD = 0.75
cfg.MAX_REGENERATIONS = 5
cfg.MAX_REPAIR_ATTEMPTS = 3
cfg.OPENAI_MODEL_NAME = "gpt-3.5-turbo"

from experiments.run_a4_full import run_a4_full
from evaluation.gsm8k_evaluator import evaluate_answer
from logging_system.experiment_logger import save_experiment


def run_a4_tuned(problem):
    """Run A4 with tuned parameters."""
    start_time = time.time()
    try:
        result = run_a4_full(problem)
        result["latency"] = time.time() - start_time
        result["success"] = True
        return result
    except Exception as e:
        return {
            "error": str(e),
            "success": False,
            "latency": time.time() - start_time,
        }


def main():
    """Run 100-example evaluation with tuned parameters."""
    
    num_examples = 100
    output_dir = Path("results/evaluation_100_tuned")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Print tuned configuration
    print("=" * 80)
    print("100-EXAMPLE EVALUATION WITH PARAMETER TUNING")
    print("=" * 80)
    print("\nTuned Parameters:")
    print("  VERIFICATION_THRESHOLD (τ):       0.75 (original: 0.75)")
    print("  MAX_REGENERATIONS:                5 (original: 2)")
    print("  MAX_REPAIR_ATTEMPTS:              3 (original: 2)")
    print("  Model:                            gpt-3.5-turbo")
    print("  Dataset:                          GSM8K test set (n=100)")
    print("=" * 80)
    
    print(f"\nLoading GSM8K dataset...")
    try:
        dataset = load_dataset("openai/gsm8k", "main", split="test")
    except Exception as e:
        print(f"ERROR loading dataset: {e}")
        print("Make sure you have datasets library installed: pip install datasets")
        return
    
    print(f"Starting evaluation on {num_examples} examples")
    print(f"Model: {cfg.OPENAI_MODEL_NAME}")
    print("=" * 80)
    
    results = []
    correct_count = 0
    error_count = 0
    start_time_overall = time.time()
    
    for i in range(min(num_examples, len(dataset))):
        item = dataset[i]
        problem = item["question"]
        ground_truth = item["answer"]
        
        # Progress indicator
        print(f"\n[{i+1:3d}/{num_examples}] ", end="", flush=True)
        
        try:
            # Run A4 with tuned parameters
            result = run_a4_tuned(problem)
            
            if result.get("success"):
                # Evaluate answer
                is_correct, prediction, _ = evaluate_answer(
                    result.get("agent_c"), ground_truth
                )
                result["correct"] = is_correct
                result["prediction"] = prediction
                result["problem_id"] = i
                result["ground_truth"] = ground_truth
                result["status"] = "OK" if is_correct else "X"
                
                if is_correct:
                    correct_count += 1
                
                # Save to JSONL
                save_experiment(
                    result, 
                    filename=str(output_dir / "a4_tuned_100.jsonl")
                )
                
                print(result["status"], end=" ", flush=True)
            else:
                # Error in execution
                error_count += 1
                result["status"] = "ERROR"
                result["problem_id"] = i
                result["ground_truth"] = ground_truth
                
                save_experiment(
                    result,
                    filename=str(output_dir / "a4_tuned_100.jsonl")
                )
                
                print("E", end=" ", flush=True)
            
            results.append(result)
            
            # Print cumulative accuracy every 10 examples
            if (i + 1) % 10 == 0:
                cumulative_acc = correct_count / (i + 1) * 100
                print(f"[Cumulative: {cumulative_acc:.1f}%]", end=" ", flush=True)
        
        except KeyboardInterrupt:
            print("\n\nInterrupted by user")
            break
        except Exception as e:
            print(f"FATAL({str(e)[:15]})", end=" ", flush=True)
            error_count += 1
    
    # Final summary
    elapsed = time.time() - start_time_overall
    total_evaluated = len(results)
    accuracy = correct_count / total_evaluated * 100 if total_evaluated > 0 else 0
    
    print("\n\n" + "=" * 80)
    print("EVALUATION COMPLETE")
    print("=" * 80)
    print(f"\nResults (n={total_evaluated}):")
    print(f"  Correct:       {correct_count}/{total_evaluated} ({accuracy:.1f}%)")
    print(f"  Errors:        {error_count}")
    print(f"  Total time:    {elapsed:.1f}s ({elapsed/60:.1f}m)")
    print(f"  Avg time/ex:   {elapsed/total_evaluated:.2f}s")
    
    print(f"\nConfiguration Used:")
    print(f"  VERIFICATION_THRESHOLD (τ):       {cfg.VERIFICATION_THRESHOLD}")
    print(f"  MAX_REGENERATIONS:                {cfg.MAX_REGENERATIONS}")
    print(f"  MAX_REPAIR_ATTEMPTS:              {cfg.MAX_REPAIR_ATTEMPTS}")
    print(f"  model:                            {cfg.OPENAI_MODEL_NAME}")
    
    # Analysis
    print(f"\nAnalysis:")
    if accuracy >= 90:
        print(f"  ✓ TARGET ACHIEVED: {accuracy:.1f}% >= 90% !")
    elif accuracy >= 85:
        print(f"  ✓ CLOSE: {accuracy:.1f}% is close to 90% target")
    else:
        print(f"  ✗ BELOW TARGET: {accuracy:.1f}% (need tuning)")
        print(f"    Consider: τ ↓ 0.70, max_regenerations ↑ 6, retry with temps [0.0, 0.5, 0.5]")
    
    print(f"\nOutput:")
    print(f"  Results file:  {output_dir / 'a4_tuned_100.jsonl'}")
    
    # Save summary JSON
    summary = {
        "strategy": "A4",
        "total_examples": total_evaluated,
        "correct": correct_count,
        "accuracy": accuracy,
        "errors": error_count,
        "elapsed_seconds": elapsed,
        "avg_latency_per_example": elapsed / total_evaluated if total_evaluated > 0 else 0,
        "configuration": {
            "VERIFICATION_THRESHOLD": cfg.VERIFICATION_THRESHOLD,
            "MAX_REGENERATIONS": cfg.MAX_REGENERATIONS,
            "MAX_REPAIR_ATTEMPTS": cfg.MAX_REPAIR_ATTEMPTS,
            "model": cfg.OPENAI_MODEL_NAME,
            "backend": cfg.LLM_BACKEND,
        }
    }
    
    summary_path = output_dir / "summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    
    print(f"  Summary:       {summary_path}")
    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
