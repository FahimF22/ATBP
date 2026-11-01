#!/usr/bin/env python
"""
Build the result tables.

    python experiments/analyze.py --natural results/natural/qwen2.5_7b/records.jsonl
    python experiments/analyze.py --injection results/injection/qwen2.5_7b/cases.jsonl
    python experiments/analyze.py --natural ... --injection ...

Prints markdown tables and writes them to summary.md next to each input file.
"""

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path


SCOPE_ORDER = ["none", "isolated", "branch", "agent", "full"]


# ---------------------------------------------------------------------------
# Statistics helpers
# ---------------------------------------------------------------------------

def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (100 * (centre - half), 100 * (centre + half))


def mcnemar_exact(b, c):
    """Two-sided exact McNemar p-value for discordant counts b, c."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    p = sum(math.comb(n, i) for i in range(0, k + 1)) / 2 ** n
    return min(1.0, 2 * p)


def pct(k, n):
    return f"{100 * k / n:.1f} ({k}/{n})" if n else "n/a"


def load(path):
    rows = []
    for line in Path(path).open(encoding="utf-8"):
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def tokens(u):
    return (u or {}).get("prompt_tokens", 0) + (u or {}).get("completion_tokens", 0)


def table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for r in rows:
        out.append("| " + " | ".join(str(x) for x in r) + " |")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Natural run
# ---------------------------------------------------------------------------

def analyze_natural(path):
    rows = load(path)
    by_sys = defaultdict(dict)
    for r in rows:
        by_sys[r["system"]][r["problem_id"]] = r
    systems = [s for s in ["a0", "a2", "a3", "a4", "a_branch", "a_agent"] if s in by_sys]
    common = set.intersection(*(set(by_sys[s]) for s in systems)) if systems else set()
    n = len(common)
    model = rows[0].get("model") if rows else "?"
    out = [f"# Natural GSM8K evaluation ({model}, {n} problems, paired)\n"]

    # accuracy
    acc_rows = []
    base = by_sys.get("a0", {})
    for s in systems:
        recs = [by_sys[s][p] for p in common]
        k = sum(r["correct"] for r in recs)
        lo, hi = wilson(k, n)
        no_ans = sum(r.get("prediction") is None for r in recs)
        if s != "a0" and base:
            b = sum(1 for p in common if by_sys[s][p]["correct"] and not base[p]["correct"])
            c = sum(1 for p in common if not by_sys[s][p]["correct"] and base[p]["correct"])
            mc = f"+{b}/-{c}, p={mcnemar_exact(b, c):.3f}"
        else:
            mc = "-"
        acc_rows.append([s.upper(), f"{k}/{n}", f"{100 * k / n:.1f}", f"[{lo:.1f}, {hi:.1f}]", no_ans, mc])
    out.append("## Accuracy\n")
    out.append(table(["System", "Correct", "Acc %", "95% Wilson CI", "No answer", "vs A0 (fixed/broken, McNemar)"], acc_rows))

    # recovery metrics
    rec_rows = []
    for s in systems:
        if s == "a0":
            rec_rows.append(["A0", "n/a", "n/a", "n/a", "n/a"])
            continue
        recs = [by_sys[s][p] for p in common]
        det = [r for r in recs if r["detected"]]
        ecr = pct(sum(not r["correct"] for r in det), len(det))
        ran = [r for r in recs if r["scope"] != "none"]
        attempts = sum(r["regeneration_attempts"] if r["discarded"] else r["repair_attempts"] for r in ran)
        succ = sum(r["successful_attempts"] for r in ran)
        rsr = pct(succ, attempts)
        cdr = pct(sum(r["collateral_changed"] for r in ran), sum(r["accepted_before"] for r in ran))
        fixed = pct(sum(bool(r["final_all_valid"]) for r in ran), len(ran))
        rec_rows.append([s.upper(), ecr, rsr, cdr, fixed])
    out.append("\n## Recovery metrics\n")
    out.append("ECR: share of examples with a detected fault that end wrong. RSR: recovery attempts "
               "accepted on re-verification. CDR: previously accepted claims that recovery rewrote or "
               "discarded. Plan accepted: recovered plans that pass verification.\n")
    out.append(table(["System", "ECR %", "RSR %", "CDR %", "Plan accepted after recovery %"], rec_rows))

    # cost
    cost_rows = []
    base_tok = None
    for s in systems:
        recs = [by_sys[s][p] for p in common]
        t = sum(tokens(r["usage"]) for r in recs) / max(n, 1)
        calls = sum(r["usage"]["calls"] for r in recs) / max(n, 1)
        secs = sum(r["usage"]["llm_seconds"] for r in recs) / max(n, 1)
        if s == "a0":
            base_tok = t
        rel = f"{t / base_tok:.2f}x" if base_tok else "-"
        cost_rows.append([s.upper(), f"{t:.0f}", rel, f"{calls:.1f}", f"{secs:.1f}"])
    out.append("\n## Cost per problem (cached calls counted at their original cost)\n")
    out.append(table(["System", "Mean tokens", "vs A0", "Mean LLM calls", "Mean model time (s)"], cost_rows))

    # A4 scope choices
    if "a4" in systems:
        recs = [by_sys["a4"][p] for p in common]
        cnt = Counter(r["scope"] for r in recs)
        acc = {sc: pct(sum(r["correct"] for r in recs if r["scope"] == sc), cnt[sc]) for sc in cnt}
        out.append("\n## A4 scope choices\n")
        out.append(table(["Scope", "Count", "Accuracy %"],
                         [[sc, cnt[sc], acc[sc]] for sc in SCOPE_ORDER if sc in cnt]))

    # where systems differ
    if systems:
        same = sum(1 for p in common if len({by_sys[s][p]["correct"] for s in systems}) == 1)
        out.append(f"\nAll systems agree on {same}/{n} problems; they differ on {n - same}.")
        det_any = sum(1 for p in common if by_sys[systems[-1]][p]["detected"])
        out.append(f"Verification flagged a fault in {det_any}/{n} initial plans.")

    text = "\n".join(out)
    Path(path).with_name("summary.md").write_text(text, encoding="utf-8")
    return text


# ---------------------------------------------------------------------------
# Injection run
# ---------------------------------------------------------------------------

def _scope_result(case, loc, scope):
    res = case[loc]["results"]
    return res.get(scope) or res["none"]   # undetected: every scope == none


def analyze_injection(path):
    cases = load(path)
    out = []
    if not cases:
        return "no cases"
    model = cases[0].get("model")
    out.append(f"# Fault-injection experiment ({model}, verifier={cases[0].get('verifier_mode')}, "
               f"{len(cases)} injected faults)\n")

    clean_path = Path(path).with_name("clean.jsonl")
    if clean_path.exists():
        clean = load(clean_path)
        n_claims = sum(c["n_claims"] for c in clean)
        fa = sum(len(c["false_alarms"]) for c in clean)
        fa_any = sum(1 for c in clean if c["false_alarms"])
        src = Counter(s for c in clean for s in c["false_alarm_sources"])
        out.append("## Verifier on clean plans (false alarms)\n")
        out.append(f"- Clean pipeline accuracy: {pct(sum(c['correct'] for c in clean), len(clean))}")
        out.append(f"- Claims wrongly flagged: {pct(fa, n_claims)}; plans with at least one false alarm: "
                   f"{pct(fa_any, len(clean))}")
        out.append(f"- False alarms by check: {dict(src)}\n")

    # detection
    groups = defaultdict(list)
    for c in cases:
        groups[(c["kind"], c["position"])].append(c)
    det_rows = []
    for (kind, pos), cs in sorted(groups.items()):
        hit = sum(c["target_detected"] for c in cs)
        extra = sum(len(set(c["detected_ids"]) - {c["injection"]["target_id"]}) for c in cs)
        det_rows.append([kind, pos, len(cs), pct(hit, len(cs)), extra])
    hit = sum(c["target_detected"] for c in cases)
    det_rows.append(["all", "all", len(cases), pct(hit, len(cases)), ""])
    out.append("## Did the verifier find the injected fault?\n")
    out.append(table(["Fault kind", "Position", "Cases", "Detected %", "Other claims flagged"], det_rows))

    for loc in ("oracle", "detected"):
        cs = [c for c in cases if loc in c]
        if not cs:
            continue
        title = ("Oracle localization (injected claim is given)" if loc == "oracle"
                 else "Detected localization (verifier decides)")
        out.append(f"\n## Recovery accuracy - {title}\n")
        headers = ["Fault kind", "Position", "N"] + [s.capitalize() for s in SCOPE_ORDER] + \
                  ["A4", "Best possible", "A4 = best scope"]
        rows = []
        sub = defaultdict(list)
        for c in cs:
            sub[(c["kind"], c["position"])].append(c)
        sub[("all", "all")] = cs
        for key in sorted(sub, key=lambda k: (k[0] == "all", k)):
            group = sub[key]
            n = len(group)
            row = list(key) + [n]
            for scope in SCOPE_ORDER:
                row.append(pct(sum(_scope_result(c, loc, scope)["correct"] for c in group), n))
            a4 = sum(_scope_result(c, loc, c[loc]["a4_scope"])["correct"] for c in group)
            row.append(pct(a4, n))
            best = 0
            a4_best = 0
            for c in group:
                corr = [s for s in SCOPE_ORDER[1:] if _scope_result(c, loc, s)["correct"]]
                if corr:
                    best += 1
                    cheapest = min(corr, key=lambda s: tokens(_scope_result(c, loc, s)["usage"]))
                    a4_best += int(c[loc]["a4_scope"] == cheapest)
                elif _scope_result(c, loc, "none")["correct"]:
                    best += 1
            row.append(pct(best, n))
            row.append(pct(a4_best, n))
            rows.append(row)
        out.append(table(headers, rows))

        # cost and collateral per scope
        cost_rows = []
        for scope in SCOPE_ORDER + ["A4"]:
            recs = [_scope_result(c, loc, c[loc]["a4_scope"] if scope == "A4" else scope) for c in cs]
            t = sum(tokens(r["usage"]) for r in recs) / len(recs)
            ran = [r for r in recs if r["scope"] != "none"]
            cdr = pct(sum(r["collateral_changed"] for r in ran), sum(r["accepted_before"] for r in ran))
            cost_rows.append([scope, f"{t:.0f}", cdr])
        out.append(f"\nCost and collateral damage ({loc}):\n")
        out.append(table(["Scope", "Mean tokens per case", "CDR %"], cost_rows))

        choice = Counter(c[loc]["a4_scope"] for c in cs)
        out.append(f"\nA4 choices ({loc}): {dict(choice)}")

        # best scope distribution by position: the core evidence for adaptivity
        best_by = defaultdict(Counter)
        for c in cs:
            corr = [s for s in SCOPE_ORDER[1:] if _scope_result(c, loc, s)["correct"]]
            if _scope_result(c, loc, "none")["correct"]:
                b = "none needed"
            elif corr:
                b = min(corr, key=lambda s: tokens(_scope_result(c, loc, s)["usage"]))
            else:
                b = "unrecoverable"
            best_by[c["position"]][b] += 1
        out.append(f"\nCheapest scope that gives a correct answer, by fault position ({loc}):\n")
        labels = ["none needed", "isolated", "branch", "agent", "full", "unrecoverable"]
        out.append(table(["Position"] + labels,
                         [[p] + [best_by[p][l] for l in labels] for p in sorted(best_by)]))

    text = "\n".join(out)
    Path(path).with_name("summary.md").write_text(text, encoding="utf-8")
    return text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--natural")
    ap.add_argument("--injection")
    args = ap.parse_args()
    if not args.natural and not args.injection:
        ap.error("give --natural and/or --injection")
    if args.natural:
        print(analyze_natural(args.natural))
        print()
    if args.injection:
        print(analyze_injection(args.injection))


if __name__ == "__main__":
    main()
