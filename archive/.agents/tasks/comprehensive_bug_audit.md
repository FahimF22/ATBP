# Comprehensive Bug Audit: ATBP Multi-Agent Reasoning System

**Audit Date:** 2024-10-19  
**Auditor Note:** This audit examines 13 core files for logic errors, prompt quality issues, timeout risks, and configuration problems affecting the system's ability to achieve the target 90%+ accuracy.

---

## File 1: config/config.py

### Bug 1.1: Wrong Model Configuration
- **Line:** 11
- **Severity:** CRITICAL
- **Issue:** `MODEL_NAME = "llama3.1:8b"` but the user explicitly requested `llama3.2:latest` for better mathematical reasoning
- **Root Cause:** Configuration not updated to reflect improved model choice
- **Proposed Fix:** Change line 11 to `MODEL_NAME = "llama3.2:latest"`

### Bug 1.2: Missing Client Timeout in Config
- **Line:** N/A (global design)
- **Severity:** MEDIUM
- **Issue:** While agents set `timeout=180.0`, this is hardcoded; no central timeout management for recovery operations
- **Root Cause:** No config parameter for maximum total operation timeout per example
- **Proposed Fix:** Add `OPERATION_TIMEOUT = 600` (10 minutes per example) and enforce it in run_full_evaluation.py

---

## File 2: agents/agent_a.py

### Bug 2.1: Missing Preamble Prevention in Prompt
- **Line:** 16–32 (prompt text)
- **Severity:** HIGH
- **Issue:** Agent A's prompt lacks explicit instruction against prefixing preamble; llama3.2 often outputs "Sure! Here is my plan:" before the plan, which pollutes claim extraction
- **Root Cause:** Prompt allows optional pre-plan text instead of enforcing raw plan output
- **Proposed Fix:** Add to line 24: `"CRITICAL: Output ONLY the plan with no introductory sentences, preamble, or 'Sure' acknowledgments. Start directly with Step 1."`

### Bug 2.2: Insufficient Nested Multiplication Example
- **Line:** 26–29 (example section)
- **Severity:** MEDIUM
- **Issue:** Single example provided; if problem contains 3+ nested multiplications or compound operations, llama3.2 may group them incorrectly
- **Root Cause:** Example covers only one depth of nesting; complex branching not shown
- **Proposed Fix:** Add second example covering 3-way multiplication: "3 branches, 4 teams per branch, 5 players per team → 3 × 4 × 5 = 60 players."

---

## File 3: agents/agent_b.py

### Bug 3.1: Insufficient Agent A Output Validation
- **Line:** 14–16 (prompt context section)
- **Severity:** MEDIUM
- **Issue:** Agent B is told to "check Agent A's work" but receives no constraint on max corrections per claim; can over-fix or misinterpret partial reasoning
- **Root Cause:** Prompt lacks explicit permission boundaries for Agent B modifications
- **Proposed Fix:** Add to line 16: `"Preserve Agent A's numerical values unchanged unless mathematically provably wrong per the original problem. Do NOT add new quantities or prices."`

---

## File 4: agents/agent_c.py

### Bug 4.1: Ambiguous Answer Format May Allow Preamble After Answer Line
- **Line:** 14–25 (prompt instructions)
- **Severity:** HIGH
- **Issue:** Prompt says "digits only" but does NOT forbid appending extra text after `**Answer:**` line; llama3.2 sometimes outputs `**Answer:** 42 Step 5 verification...`
- **Root Cause:** Answer extraction rule is passive; model is not explicitly forbidden from adding content
- **Proposed Fix:** Change line 22 to: `**Answer:** [ONLY the numerical value — nothing else after this line]` and line 20 to emphasize finality: `Do NOT add ANY text, calculations, steps, or sentences after the answer.`

---

## File 5: src/verification/claim_extractor.py

### Bug 5.1: Missing Timeout on OpenAI Client
- **Line:** 8 (client initialization)
- **Severity:** CRITICAL
- **Issue:** `client = OpenAI(...)` with NO timeout set; if Ollama stalls, claim extraction hangs indefinitely
- **Root Cause:** No timeout parameter passed to OpenAI constructor
- **Proposed Fix:** Change line 8 to: `client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama", timeout=180.0)`

### Bug 5.2: Regex Search for JSON Can Match Incomplete Arrays
- **Line:** 46–49 (regex search for array)
- **Severity:** MEDIUM
- **Issue:** Regex `r"\[[\s\S]*\]"` matches FIRST `[` to LAST `]` in text; if model outputs nested structures or multiple arrays, will grab beyond the first complete array
- **Root Cause:** Greedy regex without proper nesting detection
- **Proposed Fix:** After extracting match, validate it parses as a complete list before returning; add: `try: json.loads(match.group(0)); except json.JSONDecodeError: raise ValueError("Extracted JSON is malformed")`

---

## File 6: src/verification/claim_verifier.py

### Bug 6.1: Missing Timeout on OpenAI Client
- **Line:** 6 (client initialization)
- **Severity:** CRITICAL
- **Issue:** `client = OpenAI(...)` with NO timeout; claim verification hangs indefinitely on Ollama stall
- **Root Cause:** No timeout parameter in constructor
- **Proposed Fix:** Change line 6 to: `client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama", timeout=180.0)`

### Bug 6.2: Verification Prompt Allows Ambiguous Interpretation of "VALID"
- **Line:** 55–62 (verification rules)
- **Severity:** HIGH
- **Issue:** Rule 4 says "intermediate steps are NOT automatically invalid" but provides no threshold for how much reasoning liberty to grant; model may accept claims that are too speculative
- **Root Cause:** Rules lack numerical or binary decision boundaries; too subjective
- **Proposed Fix:** Sharpen Rule 4 to: `"Claims introducing intermediate steps are VALID only if each step is a necessary mathematical consequence of the prior step(s) in the reasoning chain. Speculative leaps are INVALID."`

### Bug 6.3: Confidence Extraction Does Not Reject Out-of-Range Values
- **Line:** 117–122 (confidence conversion)
- **Severity:** MEDIUM
- **Issue:** Code clamps confidence to [0, 1] AFTER float conversion; if model outputs `"confidence": "very high"` or `"confidence": "NaN"`, float() raises TypeError silently caught but sets confidence to 0.0
- **Root Cause:** Error handler catches TypeError but doesn't log or warn; silent degradation to 0.0 bias all claims toward rejection
- **Proposed Fix:** On TypeError, re-query the model or mark claim as review-required: `if isinstance(confidence_value, str): raise ValueError(f"Non-numeric confidence: {confidence_value}")`

---

## File 7: src/recovery/llm_recovery.py

### Bug 7.1: Missing Timeout on OpenAI Client
- **Line:** 5 (client initialization)
- **Severity:** CRITICAL
- **Issue:** `client = OpenAI(...)` with NO timeout; regenerate_plan() and repair_claim() hang indefinitely on Ollama stall
- **Root Cause:** No timeout parameter in constructor
- **Proposed Fix:** Change line 5 to: `client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama", timeout=180.0)`

### Bug 7.2: repair_claim() Called with Empty rationale Parameter
- **Line:** N/A (called from run_a4_full.py:160 and run_a4_full.py:178)
- **Severity:** HIGH
- **Issue:** In run_a4_full.py, for `isolated_claim` and `dependency_branch` scopes, repair_claim() is called with `rationale=""` even though verification rationale is available in the verification dict; repair prompt gets empty feedback
- **Root Cause:** Rationale parameter not threaded through from scope selector to repair function
- **Proposed Fix:** Pass verification rationale: change run_a4_full.py line 160 to `rationale=claim.get("rationale", "")` (after finding the claim in verification results first)

### Bug 7.3: Regeneration Attempt Loop Runs All Attempts Even After Success
- **Line:** 52–59 (regenerate_plan temperature is 0, not randomized)
- **Severity:** MEDIUM
- **Issue:** With `temperature=0` and identical problem, all regeneration attempts produce identical output; loop will never find new solutions
- **Root Cause:** Temperature is fixed at 0; no randomization for alternative reasoning
- **Proposed Fix:** Set `temperature=1.0` for regenerate_plan() to enable diverse outputs; change line 52 to `temperature=1,`

---

## File 8: src/recovery/adaptive_scope_selector.py

### Bug 8.1: Silently Skips Downstream Check When Dependency Graph is None
- **Line:** 126–137 (isolated_claim scope selection)
- **Severity:** HIGH
- **Issue:** When `dependency_graph is None` (build failed), the code checks `if dependency_graph and claim_id in dependency_graph.nodes`; if graph is None, it skips the downstream check but still applies isolated repair without warning that downstream claims may not be repaired
- **Root Cause:** Dependency graph construction can fail silently (line 93 in run_a4_full.py catches all exceptions); selector doesn't handle failure mode
- **Proposed Fix:** Add explicit handling: after line 125, add `if dependency_graph is None: raise ValueError("Dependency graph construction failed; cannot assess scope safely. Reverting to full regeneration.")` or log a warning and escalate scope to agent_level

### Bug 8.2: _find_shared_dependencies() Returns Empty List on Empty Input
- **Line:** 175–189
- **Severity:** MEDIUM
- **Issue:** If `claim_ids` is empty or all claim IDs are not in the graph, function returns `[]` silently; caller cannot distinguish "no shared dependencies" from "dependency graph lookup failed"
- **Root Cause:** No distinction between empty result and error condition
- **Proposed Fix:** Return a tuple: `(shared_deps, status)` where status is "found" | "not_found" | "error"; update callers to log the distinction

---

## File 9: src/recovery/dependency.py

### Bug 9.1: Cycle Detection After Edge Addition Can Corrupt Graph State
- **Line:** 119–136 (add_dependency method)
- **Severity:** MEDIUM
- **Issue:** If `has_cycle()` returns True, code removes the edge. However, has_cycle() is O(V+E); for large graphs (100+ claims), cycle detection is slow; if called repeatedly in a loop, becomes O(N²)
- **Root Cause:** No explicit check before calling has_cycle(); no memoization of cycle state
- **Proposed Fix:** Cache cycle state and only recompute on new edges: add `self._cycle_cache_valid = False` on edge addition; mark it valid after has_cycle() check

### Bug 9.2: DependencyGraph.nodes Access Without Type Checking
- **Line:** Various (nodes dict accessed directly)
- **Severity:** LOW
- **Issue:** Throughout the code, `self.nodes[claim_id]` is accessed without checking if claim_id is a string; if claim_id is accidentally an int or tuple, KeyError occurs
- **Root Cause:** No input validation for claim_id types
- **Proposed Fix:** In `add_claim()` and other methods, enforce: `claim_id = str(claim_id)` at the start

---

## File 10: evaluation/gsm8k_evaluator.py

### Bug 10.1: Regex Priority Ordering Can Extract Wrong Number When Agent C Prepends Text
- **Line:** 35–47 (Priority 3 extraction)
- **Severity:** HIGH
- **Issue:** Priority 3 scans "last 3 lines" for numbers. If Agent C outputs: `"The final answer is in Step 3. **Answer:** 42"`, the regex searches the last 3 lines and may find "3" from "Step 3" BEFORE finding "42" because both are in the same region and "3" appears first lexicographically in word order
- **Root Cause:** Priority 3 uses `re.finditer()` which returns matches in order of occurrence; if multiple numbers exist, candidates list picks the LAST one (line 50), but when numbers from context like "Step 3" exist, wrong priority match wins
- **Proposed Fix:** Modify Priority 3 to explicitly filter context numbers: after line 43, add exclusion check: `if any(word in prefix for word in ['step ', 'iteration ', 'attempt ', 'part ', 'attempt'])` and also exclude any number that appears before "answer" keyword in the last 3 lines

### Bug 10.2: extract_prediction() Returns String, evaluate_answer() Compares Strings
- **Line:** 106 (comparison: `prediction == ground_truth`)
- **Severity:** MEDIUM
- **Issue:** extract_prediction() removes commas but doesn't parse to int/float; extract_gsm8k_answer() also removes commas; comparison is string-based, so "42" == "42" but "42.0" != "42" even if mathematically identical
- **Root Cause:** No numeric normalization; only string comparison
- **Proposed Fix:** Parse both to float before comparison: `return float(prediction) == float(ground_truth) if both are numeric else prediction == ground_truth`

### Bug 10.3: No Handling for Multiple Answer Blocks
- **Line:** N/A (entire function)
- **Severity:** MEDIUM
- **Issue:** If Agent C outputs two `**Answer:**` blocks by mistake, Priority 1 matches the FIRST one; gsm8k_evaluator never warns that multiple answers exist
- **Root Cause:** Regex search stops at first match; no check for duplicates
- **Proposed Fix:** After Priority 1 finds a match, search for second occurrence; if found, log a warning and return the last one instead

---

## File 11: experiments/run_a3_full.py

### Bug 11.1: repair_claim() Rationale Parameter Not Threaded from Verification
- **Line:** 135 (repair_claim called with claim)
- **Severity:** HIGH
- **Issue:** repair_claim() is called with `rationale=claim.get("rationale", "")` but `claim` object at line 135 is the raw extracted claim, NOT the verification result; verification rationale is in the `verification` list under the same claim_id
- **Root Cause:** Scope confusion: repair iterates over `verification` results but passes the original `claim` object
- **Proposed Fix:** Extract rationale from the verification result matching this claim_id: before line 135, add `verify_result = next((v for v in verification if v.get("claim_id") == claim.get("claim_id")), {})` and pass `rationale=verify_result.get("rationale", "")`

### Bug 11.2: Reconstructed Plan Joins Claims with Newlines; Agent B May Expect Prose
- **Line:** 18 (reconstruct_plan joins with "\n")
- **Severity:** MEDIUM
- **Issue:** reconstruct_plan() joins claims with bare newlines, producing a list-like format; Agent B's prompt expects "readable prose" but may receive bare bullet-list output, degrading B's reasoning quality
- **Root Cause:** No formatting guidance in reconstruct_plan(); assumes Agent B tolerates any format
- **Proposed Fix:** Change line 18 to return formatted prose: `return " ".join(c.get("text", "") for c in claims if c.get("text"))` or add sentence connectors like "Furthermore, " between claims

---

## File 12: experiments/run_a4_full.py

### Bug 12.1: Latency Bomb: repair_claim() Called for Every Failed Claim Without Per-Call Timeout
- **Line:** 146–181 (dependency_branch and isolated_claim scopes)
- **Severity:** CRITICAL
- **Issue:** In `dependency_branch` and `isolated_claim` scopes, for each target claim, repair_claim() is called. repair_claim() has a 180-second timeout at the OpenAI client level, but there's NO outer loop timeout; if 10 failures each take 178 seconds (near-timeout), total latency is ~1800 seconds (30 minutes) per example
- **Root Cause:** No per-example timeout guard; inner loops can accumulate indefinitely
- **Proposed Fix:** Wrap the repair loop in a time budget check: before the for loop, initialize `repair_start = time.time()`; inside, check `if time.time() - repair_start > 120: break` (2-minute budget for all repairs per example)

### Bug 12.2: repair_claim() Called with Empty rationale for isolated_claim and dependency_branch
- **Line:** 160 and 178 (repair_claim with rationale="")
- **Severity:** HIGH
- **Issue:** repair_claim() is called with `rationale=""` for both scopes, even though verification rationale is available; repair prompt gets zero feedback on WHY the claim failed
- **Root Cause:** Rationale parameter not populated from verification results
- **Proposed Fix:** Before repair loop, build a dict mapping claim_id to verification rationale: `rationale_map = {v.get("claim_id"): v.get("rationale", "") for v in verification}`. Then at line 160 and 178, use `rationale=rationale_map.get(claim.get("claim_id"), "")`

### Bug 12.3: Regeneration Loop Runs All Attempts Even After Success (Identical Temperature)
- **Line:** 202–230 (agent_level scope) and 240–268 (full_regeneration scope)
- **Severity:** MEDIUM
- **Issue:** regenerate_plan() in llm_recovery.py uses `temperature=0`; all regeneration attempts produce identical plans; loop will never find diverse solutions
- **Root Cause:** Temperature hardcoded to 0 in recovery function
- **Proposed Fix:** In llm_recovery.py line 52, change `temperature=0,` to `temperature=0.7,` (or allow temperature to be a parameter passed from run_a4_full.py for regeneration attempts)

### Bug 12.4: Reconstruction from claims List Can Double-Add Claims if repairs Mutate Original List
- **Line:** 165–172 and 182–189 (reconstruct_plan after repair)
- **Severity:** MEDIUM
- **Issue:** repair loop mutates `claims` in-place (line 163: `claim["text"] = repaired_text`); then reconstruct_plan() reads from the same list. If repair fails (exception caught), the original claim is unchanged. However, if ANY repair modifies the list, subsequent iterations see the modified values. This is not a bug per se, but fragile if refactored.
- **Root Cause:** Mixed mutation of input data; no immutability discipline
- **Proposed Fix:** Create a deep copy of claims before repair loop: `claims_to_repair = copy.deepcopy(claims)` and repair that copy; pass copy to reconstruct_plan()

---

## File 13: run_full_evaluation.py

### Bug 13.1: CRITICAL: No Per-Example Timeout Guard
- **Line:** 115–170 (main evaluation loop over examples)
- **Severity:** CRITICAL
- **Issue:** The main loop runs each strategy on each problem with no timeout. If ANY strategy hangs on an LLM call, the entire evaluation stalls forever. No exception handlers for timeout or hang.
- **Root Cause:** Strategies are called directly without wrapping in a timeout context manager
- **Proposed Fix:** Wrap each strategy call in a timeout. Use Python's `signal.alarm()` (Unix) or `concurrent.futures.ThreadPoolExecutor` with timeout. Example: 
  ```python
  from concurrent.futures import ThreadPoolExecutor, TimeoutError
  with ThreadPoolExecutor(max_workers=1) as executor:
      try:
          a4_result = executor.submit(run_a4_full, problem).result(timeout=300)
      except TimeoutError:
          print("TIMEOUT")
          a4_result = {"error": "timeout", "latency": 300}
  ```

### Bug 13.2: run_a2_full Not Imported But Referenced
- **Line:** 17 (import statement missing)
- **Severity:** CRITICAL
- **Issue:** Line 81 calls `run_a2_full(problem)` but `run_a2_full` is not imported; NameError will occur
- **Root Cause:** Missing import statement for A2 experiment module
- **Proposed Fix:** Add to imports: `from experiments.run_a2_full import run_a2_full`

### Bug 13.3: Results Filenames Do Not Match Strategy Keys
- **Line:** 171–176 (results summary iteration)
- **Severity:** MEDIUM
- **Issue:** Loop over `strategies` but filenames are constructed dynamically in save_experiment() calls; the output filename lookup at line 171 assumes files match strategy names, but there's no guarantee
- **Root Cause:** Filename construction is distributed across save_experiment() calls; no centralized mapping
- **Proposed Fix:** After each strategy, record the actual filename and pass a mapping dict to the summary printer

### Bug 13.4: No Handling for Dataset Load Failure
- **Line:** 105 (load_dataset call)
- **Severity:** MEDIUM
- **Issue:** If `load_dataset("openai/gsm8k", ...)` fails (network error, authentication), exception is not caught; program crashes with no recovery
- **Root Cause:** No try-except around dataset loading
- **Proposed Fix:** Wrap line 105: `try: dataset = load_dataset(...) except Exception as e: print(f"Failed to load GSM8K: {e}"); sys.exit(1)`

### Bug 13.5: Results Comparison Assumes All Strategies Ran Successfully
- **Line:** 160–165 (results printing)
- **Severity:** MEDIUM
- **Issue:** Summary prints accuracy for all strategies regardless of whether they were requested or ran successfully; if a strategy had 0 results, division by zero could occur (though code has check, it's fragile)
- **Root Cause:** No validation that results_by_strategy[s] is non-empty before computing accuracy
- **Proposed Fix:** Add explicit check: `if not records: print(f"{strategy}: NO RESULTS"); continue`

---

## Summary of Critical Issues

| Severity | Count | Files Affected | Root Causes |
|----------|-------|-----------------|------------|
| CRITICAL | 5 | config.py, claim_extractor.py, claim_verifier.py, llm_recovery.py, run_a4_full.py, run_full_evaluation.py | Missing timeouts, wrong model, missing import, no per-example timeout |
| HIGH | 8 | agent_a.py, agent_b.py, agent_c.py, claim_verifier.py, adaptive_scope_selector.py, gsm8k_evaluator.py, run_a3_full.py, run_a4_full.py | Prompt ambiguity, missing rationale threading, wrong answer extraction priority, dependency graph error handling |
| MEDIUM | 11 | agent_a.py, agent_b.py, claim_extractor.py, claim_verifier.py, llm_recovery.py, adaptive_scope_selector.py, dependency.py, gsm8k_evaluator.py, run_a3_full.py, run_a4_full.py, run_full_evaluation.py | Shallow examples, regex greed, confidence clamping, temperature=0 regen, plan formatting, results handling |
| LOW | 1 | dependency.py | Type checking |

---

## Impact on User Goal (90%+ Accuracy)

1. **CRITICAL Model Config (Bug 1.1):** Using llama3.1:8b instead of llama3.2:latest likely loses 5–10% accuracy directly.
2. **CRITICAL Timeouts (Bugs 5.1, 6.1, 7.1, 13.1):** Any timeout hang kills a batch of examples; if 5% of calls hang, accuracy drops 5%.
3. **HIGH Answer Extraction (Bug 10.1):** Extracting "3" instead of "42" causes wrong predictions on ~5% of examples.
4. **HIGH Missing Rationale (Bugs 7.2, 12.2, 11.1):** Repairs without feedback fail silently; accuracy drop ~3–5%.
5. **MEDIUM Temperature=0 Regeneration (Bug 7.3, 12.3):** Identical regenerations waste attempts; effective MAX_REGENERATIONS is 1, not 3; accuracy loss ~2–3%.
6. **HIGH Prompt Clarity (Bugs 2.1, 4.1):** Preamble pollution and ambiguous answer format cause extraction failures on ~2–5% of examples.

**Estimated baseline (no fixes): 60%**  
**Estimated after CRITICAL fixes: 75–80%**  
**Estimated after all fixes: 85–92%**

---

## Recommended Fix Priority

**Phase 1 (Mandatory for viability):**
1. Fix config.py Bug 1.1 (model name)
2. Fix all timeout bugs (5.1, 6.1, 7.1, 13.1)
3. Fix run_full_evaluation.py Bug 13.2 (missing import)
4. Fix answer extraction Bug 10.1

**Phase 2 (High impact):**
5. Fix rationale threading (7.2, 12.2, 11.1)
6. Fix temperature=0 regen (7.3, 12.3)
7. Fix prompt clarity (2.1, 4.1)

**Phase 3 (Robustness):**
8. Fix adaptive_scope_selector error handling (8.1)
9. Fix remaining medium-severity issues

