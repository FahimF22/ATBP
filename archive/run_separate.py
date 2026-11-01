#!/usr/bin/env python
"""
Run each ATBP method (A0, A2, A3, A4) SEPARATELY on GSM8K.

Usage:
    python run_separate.py --method a0 --num-examples 5
    python run_separate.py --method a2 --num-examples 5
    python run_separate.py --method a3 --num-examples 5
    python run_separate.py --method a4 --num-examples 5
    python run_separate.py --method all --num-examples 5
"""

import sys
import json
import time
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from datasets import load_dataset
from agents.agent_a import agent_a
from agents.agent_b import agent_b
from agents.agent_c import agent_c
from experiments.run_a2_full import run_a2_full
from experiments.run_a3_full import run_a3_full
from experiments.run_a4_full import run_a4_full
from evaluation.gsm8k_evaluator import evaluate_answer
from logging_system.experiment_logger import save_experiment


def run_a0(problem):
    """A0: Sequential baseline (no recovery)."""
    start = time.time()
    plan = agent_a(problem)
    b_out = agent_b(problem, plan)
    c_out = agent_c(problem, plan, b_out)
    latency = time.time() - start
    return {
        "strategy": "a0_baseline",
        "agent_a": plan,
        "agent_b": b_out,
        "agent_c": c_out,
        "latency_seconds": latency,
        "success": True,
    }


def run_method(method, problem, ground_truth, example_id):
    """Run a single method on a single problem and return a result record."""
    if method == "a0":
        res = run_a0(problem)
    elif method == "a2":
        res = run_a2_full(problem)
    elif method == "a3":
        res = run_a3_full(problem)
    elif method == "a4":
        res = run_a4_full(problem)
    else:
        raise ValueError(f"Unknown method: {method}")

    is_correct, prediction, gt = evaluate_answer(res.get("agent_c"), ground_truth)
    res["correct"] = is_correct
    res["prediction"] = prediction
    res["problem_id"] = example_id
    res["ground_truth"] = ground_truth
    return res


METHOD_FILES = {
    "a0": "a0_baseline.jsonl",
    "a2": "a2_full_regeneration.jsonl",
    "a3": "a3_targeted_repair.jsonl",
    "a4": "a4_adaptive_recovery.jsonl",
}


def main():
    parser = argparse.ArgumentParser(description="Run ATBP methods separately")
    parser.add_argument("--method", type=str, required=True,
                        choices=["a0", "a2", "a3", "a4", "all"],
                        help="Which method to run")
    parser.add_argument("--num-examples", type=int, default=5,
                        help="Number of GSM8K examples")
    parser.add_argument("--output-dir", type=str, default="results/ollama_run",
                        help="Output directory for results")
    args = parser.parse_args()

    methods = ["a0", "a2", "a3", "a4"] if args.method == "all" else [args.method]
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading GSM8K dataset...")
    dataset = load_dataset("openai/gsm8k", "main", split="test")
    n = min(args.num_examples, len(dataset))
    print(f"Running {n} examples with method(s): {', '.join(methods)}")
    print(f"Output directory: {output_dir}")
    print(f"Model: llama3.2:latest (local Ollama, temperature=0)")
    print("=" * 70)

    all_results = {m: [] for m in methods}

    for method in methods:
        outfile = output_dir / METHOD_FILES[method]
        # Clear any previous results in this file
        if outfile.exists():
            outfile.unlink()

        print(f"\n{'=' * 70}")
        print(f"METHOD: {method.upper()}")
        print(f"{'=' * 70}")

        correct = 0
        for i in range(n):
            item = dataset[i]
            problem = item["question"]
            ground_truth = item["answer"]

            print(f"  Example {i+1}/{n}...", end=" ", flush=True)
            start = time.time()
            try:
                res = run_method(method, problem, ground_truth, i)
                latency = time.time() - start
                res["total_latency"] = round(latency, 2)
                save_experiment(res, filename=str(outfile))
                all_results[method].append(res)
                if res["correct"]:
                    correct += 1
                status = "CORRECT" if res["correct"] else "WRONG"
                extra = ""
                if method == "a2":
                    extra = f" | regen={res.get('regeneration_attempts', 0)}"
                elif method == "a3":
                    extra = f" | repairs={res.get('repair_attempts', 0)}"
                elif method == "a4":
                    extra = f" | scope={res.get('recovery_scope', 'n/a')}"
                print(f"{status} | {latency:.1f}s{extra}")
            except Exception as e:
                print(f"ERROR: {e}")

        acc = correct / n if n > 0 else 0
        print(f"\n  {method.upper()} Summary: {correct}/{n} = {acc*100:.1f}%")

    # Print final comparison if multiple methods
    if len(methods) > 1:
        print(f"\n{'=' * 70}")
        print("COMPARISON SUMMARY")
        print(f"{'=' * 70}")
        print(f"{'Method':<12} {'Accuracy':>10} {'Correct':>10} {'Mean Latency':>14}")
        print("-" * 50)
        for method in methods:
            records = all_results[method]
            if records:
                correct = sum(1 for r in records if r.get("correct", False))
                acc = correct / len(records)
                latencies = [r.get("latency_seconds", 0) or r.get("total_latency", 0) for r in records]
                mean_lat = sum(latencies) / len(latencies) if latencies else 0
                print(f"{method.upper():<12} {acc*100:>9.1f}% {correct:>10} {mean_lat:>13.1f}s")
        print()


if __name__ == "__main__":
    main()
