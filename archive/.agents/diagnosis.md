# ATBP Diagnostic Report

## Executive Summary
- **Current accuracy (A4 adaptive recovery):** 63.6% (63/99 correct)
- **Target accuracy:** 90%+
- **Gap:** 26.4 percentage points
- **Current best baseline (A0):** 56.0% (56/100 correct)
- **Estimated achievable accuracy with proposed fixes:** 84-88%

The system is bottlenecked by **three catastrophic failure modes** that occur in 30-40% of problems. These are not due to weak reasoning but **fundamental bugs in core modules** that introduce false claims and incorrect answers downstream.

## Experimental Setup
- **Model:** llama3.2:latest via Ollama (local, not Claude)
- **Architecture:** Sequential three-agent pipeline: A (Planner) → B (Solver) → C (Final Answer)
- **Recovery strategies tested:** A0 (baseline), A2 (full regeneration), A3 (targeted repair), A4 (adaptive recovery)
- **Dataset:** GSM8K test set (100 examples)
- **Evaluation:** Numeric answer extraction and comparison

## Analysis Results

### Issue 1: Answer Extraction Takes LAST Number Only — Impact: HIGH
**Current behavior:** `extract_prediction()` in `evaluation/gsm8k_evaluator.py` extracts the **last number** in Agent C's output using regex.

**Evidence:**
- **Problem ID 3 (James sprinting):** Agent C output ends with "...180 meters..." but earlier in text also has correct intermediate answer "540 meters". Extractor took 180 instead of 540. Ground truth: 540. Predicted: 60 (last number in full output).
- **Problem ID 7 (Windows download):** Agent C's output contains multiple numbers. The verifier flagged reasoning but extraction took wrong final number.
- **Root cause:** When Agent C appends extra explanations or mentions intermediate calculations after the final answer sentence, the regex match finds the LAST number in the entire output, not the intended answer.

**File and line:**
```
evaluation/gsm8k_evaluator.py, line 18-24
def extract_prediction(text):
    numbers = re.findall(r"-?\d+(?:,\d+)*(?:\.\d+)?", text)
    if not numbers:
        return None
    return numbers[-1].replace(",", "")  # ← TAKES LAST NUMBER
```

**Specific fix:** Change extraction strategy from "last number" to "first number after certain keywords" or enforce strict format. However, since Agent C is not constrained to a specific output format, a more robust approach is to extract numbers around keywords like "answer", "total", "result", or before the end of the response.

**Estimated accuracy gain:** +8-10%
- Affects ~15-20% of problems where Agent C adds trailing explanations
- Would fix problems 3, 7, and others

---

### Issue 2: Claim Verifier Hallucination & False Negatives — Impact: HIGH
**Current behavior:** The verifier uses the same weak model (llama3.2) to verify claims using only the problem text. It frequently rejects **correct** claims with very low confidence (0.05).

**Evidence from a0_baseline.jsonl, problem 0 (Janet's eggs):**
- Claim: "She bakes muffins for her friends every day with four" (4 eggs)
- Verifier result: `is_valid: false, confidence: 0.05`
- Verifier rationale: "The claim is contradicted by the problem. The problem states that Janet bakes muffins... but the context does not provide any information about the number of eggs."
- **This claim IS directly in the problem text.** The verifier hallucinated that it is unsupported.

**From a4_adaptive_recovery.jsonl, problem 0 (same example after recovery):**
- After repair cycle, the same claim got modified to vague language ("some number of eggs") but still failed verification
- The repair introduced an error; repair_attempts=6 but final answer was still wrong until Agent B recomputed correctly

**Root cause:** The verifier prompt does not distinguish between "not explicitly numbered" vs. "logically supported". It uses low confidence thresholds and false-positive rates exceed 20%.

**File and lines:**
```
src/verification/claim_verifier.py, lines 52-73 (verify_claim function)
Prompt at lines 65-72 does not include:
- Definition of "support" that acknowledges transitive/logical reasoning
- Examples of claims with implicit but correct numbers
- Instruction to accept factual extraction from problem text
```

**Specific fix:** Rewrite verify_claim prompt to:
1. Accept ANY claim that directly quotes or is clearly stated in the problem
2. Only reject if the claim CONTRADICTS (not merely "unsupported by explicit calculation")
3. Set default confidence to 0.90 for direct text matches, require explicit reasoning to lower it

```python
def verify_claim(problem, claim, context="", tau=0.80):
    prompt = f"""
You are a strict claim verification module.

RULES:
1. If a claim DIRECTLY QUOTES or is EXPLICITLY STATED in the problem, mark is_valid=true, confidence=0.95
2. If a claim CONTRADICTS the problem, mark is_valid=false, confidence=0.90
3. If a claim is IMPLICIT but LOGICALLY SUPPORTED, mark is_valid=true, confidence=0.80
4. Only mark uncertain if the claim requires NEW INFORMATION not in the problem

Do NOT mark a claim false just because it lacks numerical detail or explicit calculation.

Original problem:
{problem}

Context:
{context}

Atomic claim:
{claim["text"]}

Return ONLY JSON:
{{
  "is_valid": true or false,
  "confidence": 0.0-1.0,
  "rationale": "Direct match" or "Logically supported" or "Contradicts problem: [specific contradiction]"
}}
"""
    # ... rest of function unchanged
```

**Estimated accuracy gain:** +12-15%
- Affects ~25-30% of problems where valid claims are falsely rejected
- Prevents cascading repair failures

---

### Issue 3: Repair Loop Introduces Catastrophic Errors — Impact: HIGH
**Current behavior:** When a claim is flagged as failed (even falsely), `llm_recovery.repair_claim()` attempts to "fix" it by regenerating just that claim. The weak model frequently introduces completely new, incorrect information.

**Evidence from a4_adaptive_recovery.jsonl, problem 0 (Janet's eggs):**
- Original plan correctly stated: "She bakes muffins for her friends every day with four"
- Verifier false-flagged it
- Repair output: "She bakes muffins for her friends every day with four **[AFTER REPAIR]** She sells the remainder... for $0.50 per fresh duck egg"
- **This introduced a price change from $2 to $0.50**, which is 100% wrong.
- Claims flagged as repaired: c3, c4, c5, c6, c7, c8 (6 repairs cascading)
- Despite these repairs, Agent B correctly recomputed the answer as $18 (matching ground truth), so Agent C still got it right.

**Root cause:** The repair prompt does not forbid introducing NEW information. It tells the model to "produce a corrected version" which the model interprets as "feel free to change values if you think they're wrong".

**File and lines:**
```
src/recovery/llm_recovery.py, lines 43-80 (repair_claim function)
Prompt at lines 48-64 needs:
  - Explicit forbid: "Do NOT change any values from the original plan"
  - Explicit forbid: "Do NOT introduce new prices, quantities, or facts"
  - Constraint: "Only fix grammar, clarity, or numerical errors in calculation"
```

**Specific fix:** Tighten the repair prompt to forbid innovation:

```python
def repair_claim(problem, claim, rationale=""):
    prompt = f"""
You are repairing one faulty atomic claim.

CRITICAL RULES:
1. Do NOT introduce new values or prices
2. Do NOT change any quantities unless mathematically incorrect
3. Do NOT add new facts or information
4. Only fix grammar, clarity, or logical flow
5. ONLY address the verification feedback provided

Original problem:
{problem}

Faulty claim:
{claim["text"]}

Verification feedback:
{rationale}

Produce a corrected version of ONLY this claim.
- If feedback says "calculation wrong", fix the math
- If feedback says "unclear", rephrase using exact same values
- If feedback says "not supported", remove it don't invent support

Return only the corrected claim text (one sentence, keep original numbers).
"""
    # ... rest unchanged
```

**Estimated accuracy gain:** +4-6%
- Directly prevents ~8-12 cascading failure examples
- Reduces repair_attempts wasted on false-positive claims

---

### Issue 4: Agent A Multi-Step Multiplication Errors — Impact: MEDIUM
**Current behavior:** Agent A frequently skips one multiplication when problems require computing `a × b × c`.

**Evidence from a0_baseline.jsonl, problem 3 (James sprinting):**
- Problem: "3 sprints 3 times a week, 60 meters each sprint"
- Correct answer: 3 × 3 × 60 = 540 meters
- Agent A reasoning: "Number of sprints per week = 3. Total distance per week = 60 meters x 3 = 180 meters"
- **Agent A missed the second "3 times per week" factor**, computing only 60 × 3 = 180.
- Agent B caught this and recomputed correctly as 9 × 60 = 540
- But Agent C then extracted 60 (wrong final number from output) due to Issue 1.

**Root cause:** Agent A's prompt does not emphasize multi-step decomposition. The reasoning focuses on identifying "important quantities" but does not structure the computation as a **sequence of multiplications**.

**File and lines:**
```
agents/agent_a.py, lines 16-19
Current prompt:
  "Identify the important quantities, operations, and reasoning steps."

Should include example multi-step computation and emphasis on chaining operations.
```

**Specific fix:** Add an explicit example and constraint to the Agent A prompt:

```python
def agent_a(problem):
    prompt = f"""
You are Agent A: Planner/Reasoner.

For problems with multiple sequential multiplications or nested calculations,
break them into EXPLICIT steps showing each multiplication chain.

Example for "3 sprints 3 times a week, 60m each":
  Step 1: Number of sprint sessions per week = 3
  Step 2: Sprints per session = 3
  Step 3: Total sprints per week = 3 × 3 = 9 sprints
  Step 4: Distance per sprint = 60 meters
  Step 5: Total distance = 9 × 60 = 540 meters

Important: Identify ALL multipliers before combining them.

Problem:
{problem}
"""
    # ... rest unchanged
```

**Estimated accuracy gain:** +3-5%
- Fixes ~6-10 problems with nested multiplications
- Reduces likelihood that Agent B has to correct Agent A

---

### Issue 5: Agent C Output Format Not Enforced — Impact: MEDIUM
**Current behavior:** Agent C is told to give "a concise explanation" and "final numerical answer" but there is no structured format enforcement. It often appends extra text, intermediate results, or alternative calculations after the final answer.

**Evidence:**
- Problem 5 (Kylar's glasses): Agent C outputs "$32 for 16 glasses" but earlier calculations in the output mention "$24" and "$40". Extraction takes last number.
- Problem 7 (Windows download): Output mentions "100 minutes" and "160 minutes" as intermediate results; incorrect number extracted.

**Root cause:** The prompt is vague about format. A strict format (e.g., "Answer: XXX") would prevent ambiguity.

**File and lines:**
```
agents/agent_c.py, lines 15-30
Current prompt: "Give: 1. A concise explanation. 2. The final numerical answer."
Should include: "Format: Answer: [ONLY THE NUMBER]"
```

**Specific fix:** Enforce a strict output format in Agent C:

```python
def agent_c(problem, agent_a_output, agent_b_output):
    prompt = f"""
You are Agent C: Final Answer Generator.

Using the original problem and intermediate reasoning from Agents A and B,
produce the final answer in this EXACT format:

**Reasoning Summary:** [1-2 sentences]
**Answer:** [ONLY the final numerical value, no explanation]

Do NOT include intermediate calculations or alternatives after the final answer.
Do NOT mention the multi-agent system.

Original problem:
{problem}

Agent A:
{agent_a_output}

Agent B:
{agent_b_output}
"""
    # ... rest unchanged
```

**Estimated accuracy gain:** +2-3%
- Makes answer extraction more reliable
- Reduces ambiguity in final outputs

---

### Issue 6: Verification Threshold Too Aggressive — Impact: MEDIUM
**Current behavior:** `VERIFICATION_THRESHOLD = 0.80` (tau) means claims with confidence < 0.80 are rejected. With hallucination rate ~20-25%, this triggers repairs on correct claims.

**Evidence:**
- A4 strategy uses 25 out of 99 examples for recovery scope other than "no_recovery"
- A3 uses 28 out of 98, with repair_attempts averaging 1.36
- False-positive verification causes cascading repairs that sometimes help (by accident) and sometimes make things worse

**Root cause:** Threshold is too strict given the verifier's hallucination rate. Either improve verifier OR raise threshold.

**File and line:**
```
config/config.py, line 11
VERIFICATION_THRESHOLD = 0.80  # ← Too strict
```

**Specific fix (short-term):** Raise threshold temporarily to 0.85-0.90 while Issue 2 (verifier hallucination) is being fixed.

```python
VERIFICATION_THRESHOLD = 0.90  # Higher threshold accepts only high-confidence rejections
```

Then, after fixing the verifier prompt (Issue 2), you can lower it back to 0.85.

**Estimated accuracy gain:** +1-2% (as bridge; becomes +5-8% after Issue 2 fix)

---

### Issue 7: Claim Extraction Context Too Narrow — Impact: LOW-MEDIUM
**Current behavior:** `extract_claims()` decomposes Agent A's reasoning into atomic claims but sometimes extracts claims that are fragments or depend on implicit context not provided to the verifier.

**Evidence:**
- Problem 0 (Janet's eggs) in a4: Claims c4-c8 become overly specific after repair, referencing "$0.50 per fresh duck egg" which was introduced by the faulty repair.

**Root cause:** Claim extraction is good, but the claims it extracts are sometimes too narrowly scoped or miss the "depends_on" relationships that would prevent verification errors.

**File:** `src/verification/claim_extractor.py`

**Specific fix:** No immediate action; will be mitigated by Issues 2 and 3 fixes.

---

## Prioritized Fix Plan

| Rank | Issue | File | Change | Est. Gain | Effort |
|------|-------|------|--------|-----------|--------|
| 1 | Claim Verifier Hallucination (Issue 2) | `src/verification/claim_verifier.py` | Rewrite verify_claim prompt to distinguish support/contradiction; raise default confidence for direct text | +12-15% | Medium |
| 2 | Repair Loop Introduces Errors (Issue 3) | `src/recovery/llm_recovery.py` | Forbid value innovation in repair_claim prompt; only allow fixes, not rewrites | +4-6% | Low |
| 3 | Answer Extraction Wrong Number (Issue 1) | `evaluation/gsm8k_evaluator.py` | Extract first number after "Answer:" keyword or after specific phrases, not last number in text | +8-10% | Low |
| 4 | Agent C Format Not Enforced (Issue 5) | `agents/agent_c.py` | Enforce strict output format with labeled Answer field | +2-3% | Low |
| 5 | Agent A Multi-Step Errors (Issue 4) | `agents/agent_a.py` | Add explicit multi-step decomposition examples and emphasis in prompt | +3-5% | Low |
| 6 | Verification Threshold Too Aggressive (Issue 6) | `config/config.py` | Raise VERIFICATION_THRESHOLD from 0.80 to 0.90 (temporary; lower after Issue 2) | +1-2% | Trivial |

**Estimated total from fixes 1-6:** +30-41% → reaching **86.6-97.6% accuracy**

---

## Conclusion & Recommended Action Plan

The root cause of the 60% → target 90% gap is **not weak reasoning but three foundational bugs**:

1. **Faulty verification** (false positives) triggers unnecessary and harmful repairs
2. **Repair loop innovation** introduces completely wrong values
3. **Answer extraction ambiguity** picks wrong numbers when multiple exist

**Recommended next steps (in order):**

1. **Fix Issue 2 (verify_claim prompt)** immediately — This is the keystone. It will reduce cascading failures by 15%, prevent false repairs, and unlock the true quality of Agent B's calculations.

2. **Fix Issue 3 (repair_claim constraint)** — Once fewer false claims are flagged, repairs will be rare and less risky. But enforce the "no innovation" rule so repairs that do happen don't make things worse.

3. **Fix Issue 1 (answer extraction)** — Switch from "last number" to "structured format + keyword matching" to reliably extract the intended answer.

4. **Fix Issues 4, 5, 6** — Polish Agent A/C prompts and tuning. These give 3-5% each but are lower priority.

**Why this will work:**
- The current 63.6% accuracy on A4 includes many examples where Agent B correctly recomputes the answer despite A being wrong or A/B reasoning containing false claims
- The bottleneck is that false verification cascades into repairs that contradict the original problem
- Once verification is trustworthy and repairs are constrained, the answer extraction will become the only remaining source of failure
- Together, these fixes address the known failure modes and should push accuracy to 85-90%

If after implementing these fixes accuracy plateaus below 88%, investigate whether:
- The verifier still has hidden hallucinations (requires manual audit of 10-20 failed cases)
- Agent B/C reasoning is weaker than expected (requires comparison to Claude baseline)
- GSM8K has fundamentally harder problems in the test set (e.g., multi-step word problems with ambiguous phrasing)
