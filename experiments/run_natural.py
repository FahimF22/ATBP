#!/usr/bin/env python
"""
Natural-error evaluation on GSM8K: every system on the same problems.

    python experiments/run_natural.py --n 200
    python experiments/run_natural.py --n 200 --systems a0,a2,a3,a4,a_branch,a_agent
    ATBP_MODEL=llama3.1:8b python experiments/run_natural.py --n 200

Results go to results/natural/<model>/records.jsonl (one line per system per
problem). The run is resumable: rerun the same command to continue.
Each problem runs all systems before its records are written, so a stopped run
still gives paired results. --workers runs several problems at the same time.
"""

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from datasets import load_dataset  # noqa: E402

from config import config as cfg  # noqa: E402
from src.llm_client import model_id  # noqa: E402
from src.systems import run_system, SYSTEMS  # noqa: E402


def safe_name(s):
    return s.replace(":", "_").replace("/", "_")


def run_name():
    """Results folder name: the model, plus "_lean" for the token-saving variant."""
    return (safe_name(model_id()) + ("_lean" if cfg.LEAN else "")
            + ("_v2" if cfg.V2 else ""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=200, help="number of GSM8K test problems")
    ap.add_argument("--start", type=int, default=0, help="first problem index")
    ap.add_argument("--systems", default="a0,a2,a3,a4")
    ap.add_argument("--out", default=None, help="output jsonl (default results/natural/<model>/records.jsonl)")
    ap.add_argument("--workers", type=int, default=cfg.WORKERS,
                    help="problems run at the same time (default: 1 for Ollama, 8 for APIs)")
    args = ap.parse_args()

    systems = [s.strip() for s in args.systems.split(",") if s.strip()]
    for s in systems:
        if s not in SYSTEMS:
            raise SystemExit(f"unknown system {s}; choose from {SYSTEMS}")

    out = Path(args.out or ROOT / "results" / "natural" / run_name() / "records.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if out.exists():
        for line in out.open(encoding="utf-8"):
            try:
                r = json.loads(line)
                done.add((r["system"], r["problem_id"]))
            except Exception:
                continue

    ds = load_dataset("openai/gsm8k", "main", split="test")
    end = min(args.start + args.n, len(ds))
    print(f"Model {model_id()} | problems {args.start}-{end - 1} | systems {systems}")
    print(f"Writing to {out} ({len(done)} records already done) | workers {args.workers}")

    def solve(pid):
        """All systems on one problem, in order (they share cached calls)."""
        item = ds[pid]
        line, recs = [f"#{pid:4d}"], []
        for s in systems:
            if (s, pid) in done:
                line.append(f"{s}:skip")
                continue
            try:
                rec = run_system(s, item["question"], item["answer"], problem_id=pid)
            except Exception as e:
                line.append(f"{s}:ERROR({str(e)[:60]})")
                continue
            recs.append(rec)
            mark = "ok" if rec["correct"] else "X"
            line.append(f"{s}:{mark}" + (f"[{rec['scope']}]" if rec["scope"] != "none" else ""))
        return line, recs

    tally = {s: [0, 0] for s in systems}
    t0 = time.time()
    todo = [pid for pid in range(args.start, end)
            if not all((s, pid) in done for s in systems)]
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = [pool.submit(solve, pid) for pid in todo]
        for fut in as_completed(futures):
            line, recs = fut.result()
            with out.open("a", encoding="utf-8") as f:   # only this thread writes
                for rec in recs:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    tally[rec["system"]][0] += int(rec["correct"])
                    tally[rec["system"]][1] += 1
            elapsed = (time.time() - t0) / 60
            print(" ".join(line) + f"  ({elapsed:.0f} min)", flush=True)

    print("\nAccuracy this session:")
    for s, (c, n) in tally.items():
        if n:
            print(f"  {s:9s} {c}/{n} = {100 * c / n:.1f}%")
    print("Run experiments/analyze.py for the full tables.")


if __name__ == "__main__":
    main()
