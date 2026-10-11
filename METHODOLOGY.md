# ATBP Methodology: Adaptive Targeted Backtracking Protocol

**Research Project:** CSE498R - Reliability in Sequential Multi-Agent LLM Systems  
**Date:** October 2026  
**Domain:** Mathematical Reasoning (GSM8K)

---

## 1. System Architecture

### 1.1 Overview

The ATBP system evaluates error mitigation in sequential multi-agent reasoning pipelines. The baseline sequential system consists of three agents that process a mathematical word problem:

```
Input: GSM8K Problem
    ↓
[Agent A] Planner/Reasoner → Plan/Reasoning
    ↓
[Agent B] Intermediate Solver → Intermediate Solution
    ↓
[Agent C] Final Answer Synthesizer → Final Answer
    ↓
Output: Final Answer
```

Each agent receives:
- **Agent A:** Original problem text
- **Agent B:** Original problem + Agent A's reasoning
- **Agent C:** Original problem + Agent A's reasoning + Agent B's intermediate solution

The pipeline is deterministic (temperature = 0) and uses local Ollama inference (llama3.2:latest).

### 1.2 Error Propagation Problem

A single error in Agent A's reasoning can:
- Be adopted and propagated by Agent B without correction
- Lead to an incorrect intermediate solution
- Result in a final answer that is wrong despite downstream agents' attempts to correct it

ATBP aims to detect such errors early and apply targeted recovery before they propagate.

---

## 2. Claim Representation and Extraction

### 2.1 Atomic Claims

The system decomposes each agent's reasoning into **atomic claims**: the smallest independently verifiable factual or mathematical statements.

**Example:**
```
Reasoning: "The store has 12 apples. It sells 5 apples. Therefore, 7 remain."

Extracted Claims:
c1: "The store has 12 apples." (depends_on: [])
c2: "The store sells 5 apples." (depends_on: [])
c3: "Therefore, 7 remain." (depends_on: [c1, c2])
```

### 2.2 Claim Extraction Process

**Method:** LLM-based decomposition using the local Ollama model

**Input:** Agent A's reasoning text and original problem

**Process:**
1. Prompt Ollama to identify each atomic claim
2. Return JSON array with claim_id, text, depends_on list
3. Normalize and validate output

**Output Format:**
```json
[
  {
    "claim_id": "c1",
    "text": "The store has 12 apples.",
    "depends_on": []
  },
  {
    "claim_id": "c2",
    "text": "The store sells 5 apples.",
    "depends_on": []
  },
  {
    "claim_id": "c3",
    "text": "Therefore, 7 remain.",
    "depends_on": ["c1", "c2"]
  }
]
```

### 2.3 Representation Properties

- **Claim ID:** Unique identifier (c1, c2, c3, ...)
- **Text:** Claim statement verbatim from reasoning
- **Dependencies:** List of prerequisite claim IDs (empty for independent claims)
- **Verification Status:** Added post-verification (is_valid, confidence)
- **Repair Status:** Added post-repair (was_repaired, original_text)

---

## 3. Verification Procedure

### 3.1 Claim Verification

**Method:** LLM-based verification using the local Ollama model (same model as agents)

**Input:** 
- Original problem
- Problem context (agent's reasoning output)
- Atomic claim to verify

**Process:**
1. Prompt Ollama to determine if the claim is:
   - Supported by problem and context
   - Mathematically correct
   - Logically sound
2. Return: is_valid (true/false), confidence (0.0-1.0), rationale

**Output Format:**
```json
{
  "is_valid": true,
  "confidence": 0.95,
  "rationale": "The claim is directly supported by the problem statement."
}
```

### 3.2 Verification Threshold

**Threshold (τ):** 0.80

A claim is **accepted** if: `is_valid AND confidence ≥ τ`

**Rationale:** 
- Confidence <0.80 indicates uncertainty that warrants further investigation
- Setting τ=0.80 balances false positives against false negatives
- Can be adjusted via command-line parameters

### 3.3 Verification Properties

- **Deterministic:** Temperature = 0 ensures reproducibility
- **Non-calibrated:** LLM confidence scores are self-reported, not empirically calibrated
- **Single-model:** Verification uses the same Ollama model to maintain consistency
- **Context-aware:** Verification receives both original problem and agent reasoning

---

## 4. Dependency Graph

### 4.1 Representation

The dependency graph is a **directed acyclic graph (DAG)** where:

**Nodes (V):** Atomic claims  
**Edges (E):** Dependency relationships

**Edge Direction:** An edge from claim A to claim B means "B depends on A"

```
Example:
c1 → c3
c2 → c3

Interpretation: claim c3 requires both c1 and c2
```

### 4.2 Construction

1. Extract all atomic claims from agent reasoning
2. Parse the `depends_on` list from each claim
3. Add nodes to graph for each claim
4. Add directed edges for each dependency
5. Validate acyclicity (raise error if cycle detected)

**Properties:**
- Acyclic (enforced at construction time)
- May be disconnected (independent reasoning branches)
- Nodes are claims; edges represent logical prerequisites

### 4.3 Graph Queries

**Direct Dependents:** Claims directly relying on a given claim  
```python
graph.direct_dependents("c1") → {"c3"}
```

**Downstream (Transitive):** All claims transitively dependent on a given claim  
```python
graph.downstream("c1") → {"c3", "c4", ...}
```

**Direct Prerequisites:** Claims directly required by a given claim  
```python
graph.direct_prerequisites("c3") → {"c1", "c2"}
```

**Upstream (Transitive):** All claims transitively required by a given claim  
```python
graph.upstream("c3") → {"c1", "c2"}
```

**Dependency Depth:** Longest prerequisite chain  
```python
graph.dependency_depth("c3") → 1  # c3 depends on c1,c2 which have depth 0
```

---

## 5. Recovery Strategies

### 5.1 A0: Sequential Baseline (No Recovery)

**Trigger:** N/A (no verification)

**Process:**
1. Run Agent A → produce plan
2. Run Agent B with plan
3. Run Agent C with plan and intermediate solution
4. Return final answer

**Scope:** Full pipeline

**Verification:** None

**Maximum Attempts:** 1 (no regeneration)

**Output:** Final answer

### 5.2 A2: Full Regeneration

**Trigger:** ANY claim verification fails (confidence < τ OR is_valid = false)

**Decision Policy:**
- If any claim fails verification: REJECT entire Agent A output
- Discard plan completely
- Regenerate entirely new Agent A plan
- Repeat verification loop

**Scope:** Entire Agent A

**Recovery Attempts:** Up to MAX_REGENERATIONS = 3

**Verification After Recovery:** YES (verify new plan before proceeding)

**Post-Recovery Actions:**
1. If valid plan produced: continue to Agent B and C
2. If all regenerations fail: return failure record (no final answer)

**Termination:**
- Success: Valid plan produced before max attempts
- Failure: Max regenerations exceeded or no valid plan produced

**Failure Handling:** Record failure reason and incomplete results; do not generate final answer

### 5.3 A3: Fixed Targeted Repair

**Trigger:** ANY claim verification fails

**Decision Policy:**
- Identify ONLY the claims that failed verification
- Keep ALL valid claims unchanged (critical property)
- Repair each failed claim individually (one LLM call per failed claim)
- Reconstruct plan from unchanged valid claims + repaired claims

**Scope:** Only failed claims; valid claims preserved

**Recovery Attempts:** 1 per failed claim (no retry loops)

**Verification After Recovery:** YES (verify repaired claims)

**Post-Recovery Actions:**
1. Reconstruct plan from original valid + repaired claims
2. Verify repaired claims
3. Continue to Agent B and C with reconstructed plan
4. Do NOT retry repairs even if repaired claims fail verification

**Termination:** After one repair attempt per failed claim, proceed unconditionally

**Failure Handling:** Proceed with repaired plan even if repair was unsuccessful

**Critical Property:** Valid claims are NEVER re-run or modified; only failed claims are repaired

### 5.4 A4: Adaptive Targeted Recovery

**Trigger:** ANY claim verification fails

**Decision Policy:** Adaptively select repair scope based on:
1. **Failure Rate:** (failed_claims / total_claims)
2. **Single vs. Multiple:** Count of failed claims
3. **Dependency Analysis:** Whether failures share common prerequisites

**Scope Selection Algorithm:**

```
if failure_rate ≥ 50%:
    scope = "full_regeneration"
elif num_failed_claims == 1:
    if has_downstream_dependents(failed_claim):
        scope = "dependency_branch"
    else:
        scope = "isolated_claim"
else:  # Multiple scattered failures
    if shared_dependencies_exist(failed_claims):
        scope = "dependency_branch"
    else:
        scope = "agent_level"
```

**Scopes:**

| Scope | Trigger | Action | Efficiency |
|-------|---------|--------|------------|
| `no_recovery` | All valid | Proceed without repair | Minimal |
| `isolated_claim` | 1 failed, no dependents | Repair 1 claim | Low token cost |
| `dependency_branch` | Multiple failures share root | Repair all affected claims | Medium cost |
| `agent_level` | Multiple scattered failures | Regenerate Agent A (up to 3×) | Higher cost |
| `full_regeneration` | >50% claims failed | Discard and regenerate | Highest cost |

**Recovery Attempts:** 
- `isolated_claim`: 1
- `dependency_branch`: 1 per affected claim
- `agent_level`: up to MAX_REGENERATIONS = 3
- `full_regeneration`: up to MAX_REGENERATIONS = 3

**Verification After Recovery:** YES (verify after each scope application)

**Termination:** Stop after reaching acceptable verification or max attempts

**Failure Handling:** Record which scope was selected and whether it succeeded

---

## 6. Metrics and Definitions

### 6.1 Accuracy

**Definition:** Percentage of examples where final predicted answer equals ground truth

```
Accuracy = (# correct answers) / (total # examples)
```

**Calculation:** Uses standard GSM8K answer extraction (after `####` marker)

### 6.2 Error Cascade Rate (ECR)

**Definition:** Percentage of failed upstream claims that lead to final incorrect answer

```
ECR = (# examples with failed claims AND wrong final answer) / 
      (# examples with any failed claims)
```

**Numerator:** Examples where verification detected failures and final answer is wrong  
**Denominator:** Examples where verification detected ANY failure

**Interpretation:**
- ECR = 1.0: All detected failures propagated to final answer
- ECR = 0.5: Half of detected failures were corrected downstream
- ECR = 0.0: No detected failures led to wrong final answer (all corrected downstream)

### 6.3 Repair Success Rate (RSR)

**Definition:** Percentage of repaired claims that pass post-repair verification

```
RSR = (# claims still valid after repair) / (# repair attempts)
```

**Numerator:** Claims that were repaired and then verified as is_valid = true  
**Denominator:** Total number of repair attempts (for A3 and A4)

**Interpretation:**
- RSR = 1.0: All repairs succeeded
- RSR = 0.5: Half of repairs resolved the failure
- RSR = 0.0: No repairs succeeded

### 6.4 Collateral Damage Rate (CDR)

**Definition:** Percentage of originally valid claims that become invalid after repair

```
CDR = (# previously valid claims that fail post-repair) / 
      (# claims that were not repaired but were originally valid)
```

**Numerator:** Claims not repaired but verified as is_valid before and invalid after  
**Denominator:** Valid claims that were not selected for repair

**Interpretation:**
- CDR = 0.0: No collateral damage (desirable)
- CDR > 0.0: Repair introduced new errors in unrelated claims

### 6.5 Efficiency Metrics

**Token Usage:**
- Per-example: Sum of all LLM calls (agents, verification, repair, regeneration)
- Tracked at application level (requires instrumentation)
- Total tokens = initial agents + verification calls + recovery calls

**Latency:**
- Per-example: Wall-clock time from problem start to final answer
- Includes all agent calls, verification, and recovery

**Efficiency Ratio:**
- Tokens per correct answer
- Latency per correct answer
- Measures cost of improvement

### 6.6 Recovery Statistics

**Recovery Attempts:** Count of regenerations or repairs per example

**Fraction Needing Recovery:** (# examples with recovery attempts) / (total examples)

**Recovery Success Rate:** (# successful recoveries leading to correct answer) / (# recovery attempts)

---

## 7. Experimental Setup

### 7.1 Dataset

**Source:** HuggingFace `openai/gsm8k` dataset, test split

**Examples:** 1,319 total; subset evaluated per run

**Task:** Solve mathematical word problems and extract final numerical answer

**Ground Truth:** `answer` field (contains worked solution and final answer after `####`)

### 7.2 Model Configuration

**Model:** `llama3.2:latest` (local Ollama)

**Parameters:**
- Temperature: 0.0 (deterministic)
- Max tokens: 2048
- Base URL: http://localhost:11434/v1
- API Key: "ollama"

**Consistency:** Same settings across all strategies and all LLM calls

### 7.3 Verification Configuration

**Threshold (τ):** 0.80

**Max Regenerations:** 3 (for A2, A4)

**Max Repair Attempts:** 1 per failed claim (for A3, A4)

### 7.4 Reproducibility

**Determinism:** Temperature = 0 ensures same inputs → same outputs

**Seed:** Can be set for dataset sampling (default: 42)

**Example IDs:** Recorded in all results for cross-strategy comparison

**Configuration:** All settings logged in aggregate results header

---

## 8. Experimental Protocol

### 8.1 Phase 1: Smoke Test

**Goal:** Verify all components work without errors

**Dataset:** First 5 GSM8K examples

**Strategies:** A0 (baseline), A2, A3, A4

**Success Criteria:**
- All strategies complete without crashes
- Output records contain all required fields
- No silent failures

### 8.2 Phase 2: Baseline Establishment

**Goal:** Establish A0 accuracy and performance profile

**Dataset:** 100 GSM8K examples (seed=42)

**Strategy:** A0 only

**Metrics:**
- Accuracy
- Mean / median latency
- Error distribution

**Output:** `results/a0_baseline_100.jsonl`

### 8.3 Phase 3: Comparative Evaluation

**Goal:** Compare A0, A2, A3, A4 on identical examples

**Dataset:** 100 GSM8K examples (seed=42, same as Phase 2)

**Strategies:** A0, A2, A3, A4

**Metrics:** Full suite (accuracy, ECR, RSR, CDR, tokens, latency)

**Output:**
- Per-strategy JSONL files
- Aggregate CSV comparison table

### 8.4 Data Recording

**Per-Example Record Includes:**
```json
{
  "example_id": 0,
  "problem": "...",
  "ground_truth": "...",
  "strategy": "a2_full_regeneration",
  
  "agent_outputs": {
    "agent_a": "...",
    "agent_b": "...",
    "agent_c": "..."
  },
  
  "claims_and_verification": {
    "claims_initial": [...],
    "verification_before": [...],
    "claims_repaired": [...],  // If recovery applied
    "verification_after": [...]
  },
  
  "recovery": {
    "triggered": true,
    "scope": "full_regeneration",
    "attempts": 2,
    "success": true
  },
  
  "result": {
    "prediction": "7",
    "correct": true
  },
  
  "performance": {
    "latency_seconds": 5.23,
    "timestamp": "2026-10-10T..."
  }
}
```

---

## 9. Limitations and Assumptions

### 9.1 Assumptions

1. **Single-run evaluation:** Temperature = 0 means each problem is evaluated once; nondeterminism cannot be ruled out completely
2. **LLM as verifier:** Verification uses the same LLM; potential bias toward model's own reasoning
3. **Independent claims:** Claim extraction assumes claims can be decomposed independently (not always true for tightly coupled reasoning)
4. **Perfect ground truth:** Assumes GSM8K answers are all correct (minor errors may exist)

### 9.2 Limitations

1. **Verification calibration:** LLM confidence scores are self-reported and not empirically calibrated to actual accuracy
2. **Claim completeness:** LLM extraction may miss implicit claims or combine multiple claims
3. **Dependency inference:** LLM-based dependency extraction may be incomplete or incorrect
4. **Limited model:** Llama3.2 is smaller than GPT-4; performance may not generalize
5. **Fixed threshold:** τ = 0.80 is fixed; optimal threshold may vary by problem

### 9.3 Edge Cases

- **Circular reasoning:** If claim extraction produces cycles, graph construction fails
- **No claims extracted:** If extraction returns empty list, pipeline cannot proceed
- **Verifier uncertainty:** Confidence scores ≈ 0.5 are ambiguous
- **Multi-step recovery:** A4 may loop if adaptive selection always chooses ineffective scope

---

## 10. Implementation Notes

### 10.1 File Structure

```
experiments/
  run_baseline.py              # A0
  run_a2_full.py               # A2
  run_a3_full.py               # A3
  run_a4_full.py               # A4
  run_comparative.py           # Unified runner

agents/
  agent_a.py, agent_b.py, agent_c.py

src/
  verification/
    claim_extractor.py
    claim_verifier.py
  recovery/
    llm_recovery.py
    dependency.py
    adaptive_scope_selector.py

utils/
  metrics.py

results/
  a0_baseline.jsonl
  a2_full_regeneration.jsonl
  a3_targeted_repair.jsonl
  a4_adaptive_recovery.jsonl
  aggregate_comparison.csv
```

### 10.2 Error Handling

- **Import failures:** Add project root to sys.path
- **LLM timeouts:** Caught and logged with "[Error...]" marker
- **Malformed verification:** Falls back to confidence = 0.0, is_valid = false
- **Graph cycles:** Raises ValueError immediately

### 10.3 Logging

All results logged to JSONL (one record per example) with:
- ISO timestamps
- Claim extraction and verification results
- Recovery decisions and outcomes
- Full agent outputs for inspection

---

## 11. Future Work

1. **Threshold tuning:** Sensitivity analysis on τ ∈ {0.5, 0.6, 0.7, 0.8, 0.9}
2. **Calibration study:** Compare LLM confidence against actual verification accuracy
3. **Larger models:** Evaluate on GPT-4, Claude, other LLMs
4. **Batch verification:** Verify multiple claims in single LLM call
5. **Human evaluation:** Manual assessment of repaired claims vs. originals
6. **Extended domains:** Beyond GSM8K (e.g., MATH, natural QA)

---

## References

- HuggingFace GSM8K: https://huggingface.co/datasets/openai/gsm8k
- Ollama: https://ollama.ai
- OpenAI Python SDK: https://github.com/openai/openai-python

