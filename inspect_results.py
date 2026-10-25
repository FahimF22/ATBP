import sys, json
sys.path.insert(0, '.')

from pathlib import Path

for method_file in ['a0_baseline.jsonl', 'a2_full_regeneration.jsonl', 'a3_targeted_repair.jsonl', 'a4_adaptive_recovery.jsonl']:
    p = Path('results/ollama_run') / method_file
    if not p.exists():
        continue
    print(f"\n{'='*60}")
    print(f"FILE: {method_file}")
    print(f"{'='*60}")
    with open(p, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f):
            d = json.loads(line)
            print(f"\n  Example {d.get('problem_id')}: correct={d.get('correct')}")
            if 'verification_before' in d:
                vb = d.get('verification_before', [])
                print(f"    Claims extracted: {len(d.get('claims_initial', []))}")
                print(f"    Verification before:")
                for v in vb:
                    print(f"      {v.get('claim_id')}: valid={v.get('is_valid')}, conf={v.get('confidence')}")
            if 'repair_attempts' in d:
                print(f"    Repair attempts: {d.get('repair_attempts')}")
            if 'regeneration_attempts' in d:
                print(f"    Regen attempts: {d.get('regeneration_attempts')}")
            if 'recovery_scope' in d:
                print(f"    Recovery scope: {d.get('recovery_scope')}")
