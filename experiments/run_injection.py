#!/usr/bin/env python
"""
Controlled fault-injection experiment.

For each GSM8K problem:
  1. Agent A writes a plan (greedy); claims are extracted.
  2. Clean control: the clean claims are verified (false-alarm check) and
     run through B -> C.  By default only problems whose clean run is
     correct are used, so any later failure is caused by the injected fault.
  3. A fault is injected (kind x position), carried into dependent claims.
  4. The corrupted plan is run with: no recovery, and each of the four
     scopes (isolated, branch, agent, full), under
        detected localization : the verifier decides which claims are wrong
        oracle localization   : the injected claim is marked as wrong
     The A4 policy's choice is recorded for both, so its outcome can be
     compared to the best scope for that fault.

    python experiments/run_injection.py --problems 60
    python experiments/run_injection.py --problems 60 --kinds arithmetic --localization oracle

Output: results/injection/<model>/cases.jsonl (one line per injected fault).
Resumable: rerun the same command to continue.
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

from agents.agent_a import agent_a  # noqa: E402
from src.injection import KINDS, POSITIONS, choose_targets, inject, oracle_verification  # noqa: E402
from src.llm_client import model_id  # noqa: E402
from src.recovery.scopes import select_scope, safe_graph, SCOPES  # noqa: E402
from src.systems import run_system  # noqa: E402
from src.verification.claim_extractor import extract_claims, claims_to_plan  # noqa: E402
from src.verification.claim_verifier import verify_claims, failed  # noqa: E402
from config import config as cfg  # noqa: E402


SCOPE_SYSTEM = {"none": "a0", "isolated": "a3", "branch": "a_branch", "agent": "a_agent", "full": "a2"}

KEEP = ("correct", "prediction", "scope", "changed_ids", "collateral_changed", "discarded",
        "repair_attempts", "regeneration_attempts", "successful_attempts", "recovery_methods",
        "final_all_valid", "usage", "accepted_before", "n_failed_initial")


def slim(rec):
    out = {k: rec.get(k) for k in KEEP}
    out["plan_final"] = rec.get("plan_final")
    out["agent_c"] = rec.get("agent_c")
    return out


def run_conditions(problem, answer, pid, plan, claims, verification, targets, label):
    """Run 'none' and every scope from the same corrupted state."""
    results = {}
    state = (plan, claims, verification)
    for scope, system in SCOPE_SYSTEM.items():
        if scope != "none" and not (targets or failed(verification)):
            continue  # nothing detected: every scope equals 'none'
        rec = run_system(system, problem, answer, problem_id=pid, state=state,
                         targets=targets if scope != "none" else None)
        results[scope] = slim(rec)
    a4_scope, _, why, feats = select_scope(claims, verification)
    return {"results": results, "a4_scope": a4_scope, "a4_rationale": why, "features": feats}


def safe_name(s):
    return s.replace(":", "_").replace("/", "_")


def run_name():
    """Results folder name: the model, plus "_lean" for the token-saving variant."""
    return (safe_name(model_id()) + ("_lean" if cfg.LEAN else "")
            + ("_v2" if cfg.V2 else ""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--problems", type=int, default=60, help="GSM8K problems to try")
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--kinds", default=",".join(KINDS))
    ap.add_argument("--positions", default=",".join(POSITIONS))
    ap.add_argument("--localization", default="both", choices=["both", "detected", "oracle"])
    ap.add_argument("--include-wrong-clean", action="store_true",
                    help="also inject into problems the clean pipeline gets wrong")
    ap.add_argument("--out", default=None)
    ap.add_argument("--workers", type=int, default=cfg.WORKERS,
                    help="problems run at the same time (default: 1 for Ollama, 8 for APIs)")
    args = ap.parse_args()

    kinds = [k for k in args.kinds.split(",") if k]
    positions = [p for p in args.positions.split(",") if p]
    out = Path(args.out or ROOT / "results" / "injection" / run_name() / "cases.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)
    clean_out = out.with_name("clean.jsonl")

    done = set()
    if out.exists():
        for line in out.open(encoding="utf-8"):
            try:
                r = json.loads(line)
                done.add(r["case_id"])
            except Exception:
                pass
    clean_done = set()
    if clean_out.exists():
        for line in clean_out.open(encoding="utf-8"):
            try:
                clean_done.add(json.loads(line)["problem_id"])
            except Exception:
                pass

    ds = load_dataset("openai/gsm8k", "main", split="test")
    end = min(args.start + args.problems, len(ds))
    print(f"Model {model_id()} | verifier {cfg.VERIFIER_MODE} | problems {args.start}-{end - 1}")
    print(f"kinds {kinds} | positions {positions} | localization {args.localization}")
    print(f"Writing to {out} | workers {args.workers}")
    t0 = time.time()

    def process(pid):
        """Clean control plus every injected case for one problem.
        Returns (clean_record or None, [case records], [log lines])."""
        item = ds[pid]
        problem, answer = item["question"], item["answer"]
        logs, cases = [], []
        plan = agent_a(problem)
        try:
            claims = extract_claims(problem, plan)
        except Exception as e:
            return None, [], [f"#{pid}: claim extraction failed ({e})"]
        if not claims:
            return None, [], []
        graph = safe_graph(claims)

        # ---- clean control --------------------------------------------
        clean_plan = claims_to_plan(claims)
        clean_ver = verify_claims(problem, claims, context=clean_plan)
        clean = run_system("a0", problem, answer, problem_id=pid, state=(clean_plan, claims, clean_ver))
        clean_rec = None
        if pid not in clean_done:
            clean_rec = {
                "problem_id": pid, "correct": clean["correct"], "n_claims": len(claims),
                "false_alarms": [v["claim_id"] for v in failed(clean_ver)],
                "false_alarm_sources": [v.get("source") for v in failed(clean_ver)],
                "verification": clean_ver, "usage": clean["usage"],
            }
        if not clean["correct"] and not args.include_wrong_clean:
            return clean_rec, [], [f"#{pid}: clean run wrong, skipped"]

        # ---- injected faults -------------------------------------------
        for kind in kinds:
            targets = choose_targets(problem, claims, kind, graph)
            for position in positions:
                if position not in targets:
                    continue
                case_id = f"{pid}-{kind}-{position}"
                if case_id in done:
                    continue
                try:
                    bad_claims, info = inject(problem, claims, targets[position], kind,
                                              seed=cfg.BASE_SEED + pid, graph=graph)
                except Exception as e:
                    logs.append(f"#{pid} {kind}/{position}: injection failed ({e})")
                    continue
                bad_plan = claims_to_plan(bad_claims)
                det_ver = verify_claims(problem, bad_claims, context=bad_plan)
                det_ids = [v["claim_id"] for v in failed(det_ver)]

                case = {
                    "case_id": case_id, "problem_id": pid, "kind": kind, "position": position,
                    "model": model_id(), "verifier_mode": cfg.VERIFIER_MODE,
                    "injection": info, "n_claims": len(claims),
                    "detected_ids": det_ids,
                    "detected_sources": [v.get("source") for v in failed(det_ver)],
                    "target_detected": info["target_id"] in det_ids,
                    "clean_correct": clean["correct"],
                    "corrupted_plan": bad_plan,
                }
                if args.localization in ("both", "detected"):
                    case["detected"] = run_conditions(problem, answer, pid, bad_plan, bad_claims,
                                                      det_ver, None, "detected")
                if args.localization in ("both", "oracle"):
                    o_ver = oracle_verification(bad_claims, info["target_id"], info)
                    case["oracle"] = run_conditions(problem, answer, pid, bad_plan, bad_claims,
                                                    o_ver, [info["target_id"]], "oracle")
                cases.append(case)

                summary = []
                for loc in ("detected", "oracle"):
                    if loc in case:
                        res = case[loc]["results"]
                        summary.append(loc[:3] + ":" + "".join(
                            f"{s[0].upper()}{'+' if res[s]['correct'] else '-'}" for s in res)
                            + f" a4={case[loc]['a4_scope']}")
                logs.append(f"#{pid} {kind}/{position} down={info['n_down']} "
                            f"caught={case['target_detected']} | " + " | ".join(summary))
        return clean_rec, cases, logs

    def run_safely(pid):
        try:
            return process(pid)
        except Exception as e:
            return None, [], [f"#{pid}: ERROR ({str(e)[:100]})"]

    # Several problems at once; each problem's steps still run in order.
    # Only this (main) thread writes the output files.
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = [pool.submit(run_safely, pid) for pid in range(args.start, end)]
        for fut in as_completed(futures):
            clean_rec, cases, logs = fut.result()
            if clean_rec is not None:
                with clean_out.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(clean_rec, ensure_ascii=False) + "\n")
            if cases:
                with out.open("a", encoding="utf-8") as f:
                    for case in cases:
                        f.write(json.dumps(case, ensure_ascii=False) + "\n")
            for msg in logs:
                print(msg + f"  ({(time.time() - t0) / 60:.0f} min)", flush=True)

if __name__ == "__main__":
    main()
