#!/usr/bin/env python
"""
Analyze evaluation results and generate comparison report.

Usage:
    python analyze_results.py [--input-dir=results] [--output=results/analysis.txt]
"""

import sys
sys.path.insert(0, '.')

import json
import csv
import argparse
from pathlib import Path
from utils.metrics import aggregate_strategy_results


def main():
    """Analyze results."""
    
    parser = argparse.ArgumentParser(description="Analyze evaluation results")
    parser.add_argument("--input-dir", type=str, default="results", help="Input directory")
    parser.add_argument("--output", type=str, default="results/analysis.txt", help="Output file")
    
    args = parser.parse_args()
    
    input_dir = Path(args.input_dir)
    output_file = Path(args.output)
    
    # Find all result files
    result_files = {}
    for strategy in ["a0_baseline", "a2_full_regeneration", "a3_targeted_repair", "a4_adaptive_recovery"]:
        for f in input_dir.glob(f"*{strategy}*.jsonl"):
            result_files[strategy] = f
            break
    
    if not result_files:
        print("No result files found!")
        return
    
    # Analysis output
    output = []
    output.append("=" * 80)
    output.append("ATBP EVALUATION ANALYSIS REPORT")
    output.append("=" * 80)
    output.append("")
    
    # Load and analyze each strategy
    all_results = {}
    
    for strategy, filepath in sorted(result_files.items()):
        print(f"Analyzing {strategy}...")
        
        records = []
        try:
            with open(filepath) as f:
                for line in f:
                    records.append(json.loads(line))
        except Exception as e:
            output.append(f"ERROR reading {filepath}: {e}")
            continue
        
        if not records:
            output.append(f"{strategy}: No records found")
            continue
        
        all_results[strategy] = records
        
        # Calculate metrics
        agg = aggregate_strategy_results(strategy, records)
        
        output.append(f"\n{strategy.upper()}")
        output.append("-" * 80)
        output.append(f"Examples: {agg['num_examples']}")
        output.append(f"Correct: {sum(1 for r in records if r.get('correct', False))}")
        output.append(f"Accuracy: {agg['accuracy']:.2%}")
        output.append(f"")
        output.append("Metrics:")
        output.append(f"  Error Cascade Rate (ECR):    {agg['error_cascade']['ecr']:.2%}")
        output.append(f"  Repair Success Rate (RSR):   {agg['repair_success']['rsr']:.2%}")
        output.append(f"  Collateral Damage Rate (CDR):{agg['collateral_damage']['cdr']:.2%}")
        output.append(f"  Mean Latency:                {agg['efficiency']['mean_latency_seconds']:.2f}s")
        output.append(f"  Median Latency:              {agg['efficiency']['median_latency_seconds']:.2f}s")
        output.append(f"")
        output.append("Recovery Statistics:")
        output.append(f"  Examples needing recovery:   {agg['recovery']['examples_needing_recovery']}")
        output.append(f"  Mean recovery attempts:      {agg['recovery']['mean_recovery_attempts']:.2f}")
    
    # Comparison
    output.append("\n" + "=" * 80)
    output.append("STRATEGY COMPARISON")
    output.append("=" * 80)
    output.append("")
    
    if all_results:
        output.append("Accuracy Ranking:")
        accuracies = []
        for strategy, records in all_results.items():
            agg = aggregate_strategy_results(strategy, records)
            accuracies.append((strategy, agg['accuracy']))
        
        for rank, (strategy, accuracy) in enumerate(sorted(accuracies, key=lambda x: x[1], reverse=True), 1):
            output.append(f"  {rank}. {strategy:35s}: {accuracy*100:5.1f}%")
        
        # Compare against A0
        if "a0_baseline" in all_results:
            a0_accuracy = aggregate_strategy_results("a0_baseline", all_results["a0_baseline"])['accuracy']
            
            output.append(f"\nImprovement vs A0 Baseline ({a0_accuracy*100:.1f}%):")
            for strategy, records in all_results.items():
                if strategy != "a0_baseline":
                    agg = aggregate_strategy_results(strategy, records)
                    improvement = ((agg['accuracy'] - a0_accuracy) / a0_accuracy) * 100
                    output.append(f"  {strategy:35s}: {improvement:+.1f}%")
    
    # Save output
    output_text = "\n".join(output)
    print("\n" + output_text)
    
    with open(output_file, "w") as f:
        f.write(output_text)
    
    print(f"\nAnalysis saved to: {output_file}")
    
    # Generate CSV comparison
    csv_file = Path(args.input_dir) / "comparison.csv"
    if all_results:
        with open(csv_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Strategy", "Examples", "Correct", "Accuracy (%)",
                "ECR (%)", "RSR (%)", "CDR (%)",
                "Mean Latency (s)", "Recovery Examples", "Mean Recovery Attempts"
            ])
            
            for strategy, records in sorted(all_results.items()):
                agg = aggregate_strategy_results(strategy, records)
                writer.writerow([
                    strategy,
                    agg['num_examples'],
                    sum(1 for r in records if r.get('correct', False)),
                    f"{agg['accuracy']*100:.1f}",
                    f"{agg['error_cascade']['ecr']*100:.1f}",
                    f"{agg['repair_success']['rsr']*100:.1f}",
                    f"{agg['collateral_damage']['cdr']*100:.1f}",
                    f"{agg['efficiency']['mean_latency_seconds']:.2f}",
                    agg['recovery']['examples_needing_recovery'],
                    f"{agg['recovery']['mean_recovery_attempts']:.2f}",
                ])
        
        print(f"CSV comparison saved to: {csv_file}")


if __name__ == "__main__":
    main()
