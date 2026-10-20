# ATBP Codebase Audit Report
## Comprehensive Bug Inventory with Line Numbers and Severity

---

## CRITICAL ISSUES

### [BUG #1] Inconsistent LLM Client Usage: Dual APIs (HIGH → Functional but Problematic)
**Severity:** HIGH (Note: Module exists, so not blocking, but creates architectural inconsistency)  
**Files Affected:** agents/agent_a.py, agents/agent_b.py, agents/agent_c.py vs atbp_complete_pipeline.py  
**Line Numbers:**
- agent_a.py, agent_b.py, agent_c.py: Line 1 (uses `src.llm_client`)
- atbp_complete_pipeline.py: Lines 30, 508-531 (uses OpenAI SDK directly)

**Description:**  
The codebase has TWO separate LLM client implementations in parallel:
1. **Agent modules** (A, B, C) use the abstracted `src.llm_client.call_llm()` interface
2. **Main pipeline** (`atbp_complete_pipeline.py`) directly instantiates and uses OpenAI SDK

This means the agents operate through a different code path than the main ATBP logic, making them incompatible when integrated. The `src.llm_client` supports Ollama/Gemini/OpenAI but the pipeline's `LLMClient` class hardcodes different behavior.

**Current Code Snippet:**
```python
# agent_a.py, line 1
from src.llm_client import call_llm

# atbp_complete_pipeline.py, lines 508-531 (separate implementation)
class LLMClient:
    def __init__(self, config: ATBPConfig):
        self.config = config
        self.client = OpenAI(base_url=config.base_url, api_key=config.api_key)
        # ...
```

**Impact:**
- **Architectural inconsistency:** Two LLM client systems that don't communicate
- **Integration failure:** Agents cannot be directly called from the pipeline without adapter code
- **Configuration divergence:** `src.llm_client` reads from config.py, but pipeline uses ATBPConfig
- **Token tracking mismatch:** Pipeline instruments tokens in LLMClient, agents return token counts via tuple
- **Difficult debugging:** Call paths are not unified, making tracing and logging inconsistent

**Recommended Fix:**
Unify the LLM client interface — either:
- Option A: Make pipeline use `src.llm_client.call_llm()` instead of direct OpenAI SDK
- Option B: Refactor agents to directly use pipeline's LLMClient class
- Option C: Create a common abstraction that both pipeline and agents delegate to

---

### [BUG #2] OpenAI API Configuration Mismatch (CRITICAL)
**Severity:** CRITICAL  
**File:** config/config.py  
**Line Numbers:** Lines 8-9, 20-21

**Description:**  
The config module hardcodes Ollama settings as defaults while also loading an OpenAI API key from `.env`. However, the pipeline initialization in `atbp_complete_pipeline.py` (line 1061) defaults to Ollama endpoint, not OpenAI. This creates a configuration trap where `.env` has a valid OpenAI key but the system tries to use Ollama.

**Current Code Snippet:**
```python
# config/config.py, lines 8-9 (Ollama hardcoded)
API_KEY    = "ollama"
MODEL_NAME = "qwen2.5:7b"

# config/config.py, lines 20-21 (OpenAI loaded but not used)
OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL_NAME = "gpt-4o-mini"

# atbp_complete_pipeline.py, lines 58-60 (ATBPConfig defaults)
@dataclass
class ATBPConfig:
    base_url: str = "http://localhost:11434/v1"  # Ollama endpoint
    api_key: str = "ollama"
```

**Impact:**
- System will attempt to connect to Ollama on localhost:11434, which may not be running
- OpenAI key in `.env` is loaded but never used, indicating incomplete migration
- User confusion about which LLM backend is actually being used

**Recommended Fix:**
Update `ATBPConfig` to use OpenAI API key and endpoint from config/config.py or environment, or provide clear selection logic in main().

---

## HIGH SEVERITY ISSUES

### [BUG #3] Claim Repair Has No Retry Logic / Single Attempt Only (HIGH)
**Severity:** HIGH  
**File:** atbp_complete_pipeline.py  
**Line Numbers:** Lines 589-605

**Description:**  
The `repair_isolated_claim()` method attempts to repair a faulty claim exactly ONE time. There is no retry loop or fallback if the repair fails verification. This violates the ATBP design requirement that repair attempts should persist up to a specified max (configured as `max_regenerations = 3` in config).

**Current Code Snippet:**
```python
# Lines 589-605
def repair_isolated_claim(self, problem: str, graph: DependencyGraph, cid: str) -> bool:
    """Repair single faulty claim c_f and re-verify it."""
    claim = graph.claims[cid]
    prereq_ids = graph.get_prerequisites(cid)
    prereq_text = "\n".join(f"- [{pid}] {graph.claims[pid].text}" for pid in prereq_ids) or "None"

    prompt = PROMPTS["isolated_claim_repair"].format(
        problem=problem,
        prerequisite_claims=prereq_text,
        claim_id=cid,
        faulty_claim_text=claim.text,
        verifier_reason=claim.reason
    )

    raw = self.llm.generate(prompt, temperature=0.2, seed=self.config.base_seed + 1, json_mode=True)
    data = self.llm.parse_json_safely(raw)
    new_text = str(data.get("repaired_text", "")).strip()

    if new_text:
        claim.text = new_text

    self.verify_claim(problem, graph, cid)
    return claim.accepted
```

**Impact:**
- Repair attempts are not persistent across multiple seeds/temperatures
- A single LLM generation failure leaves the fault unresolved
- Metric `RSR` (Repair Success Rate) cannot reach high values because only 1 attempt is made
- Violates ATBP specification which requires up to 3 regeneration attempts

**Recommended Fix:**
Wrap repair generation in a retry loop (e.g., up to `self.config.max_regenerations` attempts) with varying seeds, similar to how A2 handles full regenerations (lines 754-772).

---

### [BUG #4] Branch Repair Has No Fallback to Full Regeneration (HIGH)
**Severity:** HIGH  
**File:** atbp_complete_pipeline.py  
**Line Numbers:** Lines 607-670

**Description:**  
The `repair_dependency_branch()` method attempts to recompute a faulty branch once. If the branch repair fails verification (i.e., all claims in the branch are not accepted), the method returns `(False, ...)` but the caller does not fall back to full regeneration or other recovery strategies. This creates a dead-end where recovery is attempted but fails without escalation.

**Current Code Snippet:**
```python
# Lines 607-670
def repair_dependency_branch(self, problem: str, graph: DependencyGraph, root_cid: str) -> Tuple[bool, int]:
    """
    Recompute faulty claim root_cid and all its downstream dependents Down(root_cid).
    Returns (branch_accepted, num_previously_valid_claims_rewritten).
    """
    # ... setup code ...
    
    raw = self.llm.generate(prompt, temperature=0.3, seed=self.config.base_seed + 2, json_mode=True)
    data = self.llm.parse_json_safely(raw)
    repaired_items = data.get("repaired_branch", [])

    if isinstance(repaired_items, list):
        for item in repaired_items:
            if isinstance(item, dict):
                rcid = str(item.get("id", ""))
                rtext = str(item.get("text", "")).strip()
                if rcid in branch_ids and rtext:
                    graph.claims[rcid].text = rtext

    branch_ok = True
    for cid in branch_ids:
        self.verify_claim(problem, graph, cid)
        if not graph.claims[cid].accepted:
            branch_ok = False

    return branch_ok, valid_downstream_rewritten
    # NOTE: If branch_ok == False, there is NO fallback or retry.
```

**Impact:**
- If branch repair fails, recovery stops without escalation to full regeneration
- CDR (Collateral Damage Rate) may be inflated if a branch repair touches many claims but fails
- A4 system (Adaptive Recovery) cannot recover from failed branch repairs

**Recommended Fix:**
When `repair_dependency_branch()` returns `False`, caller should either retry with higher temperature/different seed or escalate to full regeneration (R_full scope).

---

### [BUG #5] Token Tracking Can Receive None Values (HIGH)
**Severity:** HIGH  
**File:** atbp_complete_pipeline.py  
**Line Numbers:** Lines 519-531

**Description:**  
The `LLMClient.generate()` method updates token counts only if `response.usage` exists AND each token attribute is truthy. However, the OpenAI SDK may return `None` for token counts in some scenarios (e.g., streaming, fallback modes, or API errors). The current code does not handle this gracefully.

**Current Code Snippet:**
```python
# Lines 519-531
def generate(self, prompt: str, temperature: float = 0.0, seed: Optional[int] = None, json_mode: bool = False) -> str:
    # ... API call setup ...
    try:
        response = self.client.chat.completions.create(**kwargs)
        if getattr(response, "usage", None):
            self.prompt_tokens += (response.usage.prompt_tokens or 0)
            self.completion_tokens += (response.usage.completion_tokens or 0)
            self.total_tokens += (response.usage.total_tokens or 0)
        return response.choices[0].message.content or ""
    except Exception as e:
        logger.error(f"LLM API call failed: {e}")
        raise
```

**Impact:**
- If token counts are None, they silently default to 0 instead of raising an error or warning
- Mean token usage metrics (lines 988-989) will be artificially low
- No visibility into whether token tracking is actually working
- Reported metrics will be inaccurate if many API responses lack usage stats

**Recommended Fix:**
Log a warning if token counts are None, and consider a fallback estimation based on prompt/completion lengths.

---

### [BUG #6] JSON Parsing May Fail on Malformed Structures Without Recovery (HIGH)
**Severity:** HIGH  
**File:** atbp_complete_pipeline.py  
**Line Numbers:** Lines 533-549

**Description:**  
The `parse_json_safely()` method attempts to extract JSON from LLM responses using regex and json.loads(), but if both strategies fail, it returns an empty dict `{}` without logging or context about the parsing failure. This silent failure propagates downstream, causing claims, repairs, or verifications to silently produce invalid results.

**Current Code Snippet:**
```python
# Lines 533-549
@staticmethod
def parse_json_safely(raw_text: str) -> Dict[str, Any]:
    """Extract JSON object robustly even if wrapped in markdown code blocks."""
    text = raw_text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass

    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            pass

    return {}  # Silent failure: no warning or context
```

**Impact:**
- LLM responses that fail to parse as JSON are silently converted to empty dicts
- Downstream code (e.g., claim extraction, verifier) receives `{}` instead of expected fields
- No diagnostic information about what the LLM actually returned
- Silent data loss makes debugging extremely difficult
- Metrics become unreliable because missing claims/verifications go unnoticed

**Recommended Fix:**
Log a warning when JSON parsing fails, include the raw response snippet, and consider raising an exception or returning a sentinel value.

---

### [BUG #7] Answer Extraction Regex Misses Common Number Formats (HIGH)
**Severity:** HIGH  
**File:** atbp_complete_pipeline.py  
**Line Numbers:** Lines 808-823

**Description:**  
The `extract_final_number()` regex pattern `r"[-+]?\d*\.?\d+"` does NOT correctly match:
1. **Negative numbers in some contexts** (e.g., `-1.5e-2` scientific notation requires special handling)
2. **Scientific notation** (e.g., `1.5e10`, `2E-3`) — the current regex will only capture the mantissa, not the exponent
3. **Decimal edge cases** (e.g., `.5` without leading zero, or numbers like `1.` without trailing digits)

**Current Code Snippet:**
```python
# Lines 808-823
@staticmethod
def extract_final_number(text: str) -> Optional[float]:
    if not text:
        return None

    # Check explicit GSM8K marker #### <number>
    marker_match = re.search(r"####\s*([-+]?\d*\.?\d+)", text.replace(",", ""))
    if marker_match:
        try:
            return float(marker_match.group(1))
        except ValueError:
            pass

    # Fallback: last number in response (as described in Section VIII-D)
    nums = re.findall(r"[-+]?\d*\.?\d+", text.replace(",", ""))
    if nums:
        try:
            return float(nums[-1])
        except ValueError:
            return None

    return None
```

**Impact:**
- Scientific notation answers (common in physics/chemistry problems) will be partially extracted
- Example: `1.5e10` → regex captures only `1.5` and misses exponent
- Negative scientific notation like `-2e-3` will fail
- This causes incorrect grading for valid answers in scientific notation
- Final-answer accuracy metrics will be underestimated

**Recommended Fix:**
Use a more robust regex pattern:  
`r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"` or leverage `float()` parsing directly on candidate substrings.

---

## MEDIUM SEVERITY ISSUES

### [BUG #8] Metric Calculation Issues: Double-Counting and Boundary Cases (MEDIUM)
**Severity:** MEDIUM  
**File:** atbp_complete_pipeline.py  
**Line Numbers:** Lines 981-1009, 1013-1024

**Description:**  
The metric computation has several issues:

1. **ECR Calculation (Line 990-994):** Only includes examples where `initial_detected_fault == True`. However, this doesn't account for faults detected during intermediate repair steps (e.g., branch repair failing). ECR may under-count cascaded errors.

2. **CDR Calculation (Line 1002-1006):** Counts only `correct_units_altered` from fault_traces. But if a trace had no initial fault (`initial_detected_fault == False`), any downstream errors are not reflected in CDR. CDR may not represent true collateral damage.

3. **Division by Zero Prevention:** Uses `or 0` defaults, but does not distinguish between "0 attempts made" and "all attempts failed" in RSR reporting.

**Current Code Snippet:**
```python
# Lines 990-994 (ECR)
fault_traces = [t for t in traces if t.initial_detected_fault]
n_fault_examples = len(fault_traces)
n_cascaded = sum(1 for t in fault_traces if not t.is_correct)
ecr_str = f"{(n_cascaded / n_fault_examples * 100.0):.1f}% ({n_cascaded}/{n_fault_examples})" if n_fault_examples > 0 else "0.0% (0/0)"

# Lines 1002-1006 (CDR)
total_exposed = sum(t.correct_units_exposed for t in fault_traces)
total_altered = sum(t.correct_units_altered for t in fault_traces)
cdr_str = f"{(total_altered / total_exposed * 100.0):.1f}% ({total_altered}/{total_exposed})" if total_exposed > 0 else "0.0% (0/0)"
```

**Impact:**
- ECR (Error Cascade Rate) may be biased toward examples with early detection
- CDR (Collateral Damage Rate) calculation is incomplete
- Metrics reported in evaluation tables may not accurately reflect system behavior
- Difficult to compare results against baseline systems if metrics are computed inconsistently

**Recommended Fix:**
Clarify metric definitions and ensure all traces (not just fault_traces) contribute appropriately to ECR and CDR computations.

---

### [BUG #9] Hardcoded Prompts Without System-Level Directive (MEDIUM)
**Severity:** MEDIUM  
**File:** atbp_complete_pipeline.py  
**Line Numbers:** Lines 69-188

**Description:**  
All prompts in the `PROMPTS` dictionary are hardcoded as constants. There is no centralized system-level instruction directive that guides all LLM calls toward consistent behavior, determinism, and output format. Each prompt independently specifies format requirements, but there is no unified "system prompt" enforcing global constraints (e.g., "Always respond in valid JSON", "Never include speculation", etc.).

**Current Code Snippet:**
```python
# Lines 69-72
PROMPTS = {
    "agent_a": """You are Agent A, the Mathematical Planner and Reasoner in a sequential multi-agent system.
    ...
```

**Impact:**
- Inconsistent LLM behavior across prompts
- If a prompt is changed, it's not clear which global constraints still apply
- No unified way to add system-level guardrails (e.g., "Be concise", "Avoid speculation")
- Difficult to maintain and evolve the prompt engineering strategy
- JSON parsing failures are harder to diagnose because format expectations are local to each prompt

**Recommended Fix:**
Introduce a `SYSTEM_PROMPT` constant that applies to all LLM calls, and refactor PROMPTS to assume this context.

---

### [BUG #10] Missing Error Recovery: No LLM Retry Logic on Failure (MEDIUM)
**Severity:** MEDIUM  
**File:** atbp_complete_pipeline.py  
**Line Numbers:** Lines 519-531, entire pipeline execution flow

**Description:**  
The `LLMClient.generate()` method catches exceptions and immediately re-raises them. There is no built-in retry logic for transient API failures, rate limiting, or temporary service degradation. The entire pipeline will halt on a single LLM API error, with no graceful degradation or fallback.

**Current Code Snippet:**
```python
# Lines 519-531
try:
    response = self.client.chat.completions.create(**kwargs)
    if getattr(response, "usage", None):
        self.prompt_tokens += (response.usage.prompt_tokens or 0)
        self.completion_tokens += (response.usage.completion_tokens or 0)
        self.total_tokens += (response.usage.total_tokens or 0)
    return response.choices[0].message.content or ""
except Exception as e:
    logger.error(f"LLM API call failed: {e}")
    raise  # Immediate failure, no retry
```

**Impact:**
- Transient network errors (e.g., timeout, 503) will crash the entire evaluation run
- No exponential backoff or retry delay
- Evaluation pipeline cannot be resilient to temporary API issues
- Running large-scale GSM8K evaluation (100+ examples) is risky because any API hiccup fails the entire run
- User loses partial progress and must restart from the beginning

**Recommended Fix:**
Implement exponential backoff retry logic with configurable max attempts and delay.

---

### [BUG #11] Claim Repair Convergence: No Escalation When Repair Fails (MEDIUM)
**Severity:** MEDIUM  
**File:** atbp_complete_pipeline.py  
**Line Numbers:** Lines 816-835 (A3 system)

**Description:**  
In system A3 (Verify + Isolated Claim Repair), the loop attempts to repair each faulty claim once. If a repair fails (returns `False`), the loop simply continues to the next faulty claim without escalation or alternative recovery strategy. There is no fallback to branch repair or full regeneration if isolated repair fails.

**Current Code Snippet:**
```python
# Lines 816-835 (A3 system)
if system_name == "A3":
    if not all_ok:
        trace.correct_units_exposed = initial_valid_count
        trace.correct_units_altered = 0

        faulty_ids = [cid for cid in graph.order if not graph.claims[cid].accepted]

        for f_cid in faulty_ids:
            trace.repair_attempts += 1
            trace.selected_scopes.append("R_claim")

            if self.repair_isolated_claim(problem, graph, f_cid):
                trace.successful_repairs += 1
            # NOTE: If repair_isolated_claim returns False, no fallback or retry occurs
```

**Impact:**
- Repair Success Rate (RSR) for A3 is artificially low because no escalation strategy exists
- A faulty claim that cannot be repaired in isolation is left unresolved
- Pipeline continues with unresolved faults, leading to incorrect downstream calculations
- Undermines the purpose of A3 variant, which should provide **at least** isolated repair as an attempt

**Recommended Fix:**
If isolated claim repair fails, retry with higher temperature or different seed, or escalate to branch repair.

---

## LOW SEVERITY ISSUES

### [BUG #12] Configuration Parameter Inconsistency (LOW)
**Severity:** LOW  
**File:** config/config.py  
**Line Numbers:** Lines 15, 17

**Description:**  
The config module defines `MAX_REGENERATIONS = 2` but the `ATBPConfig` dataclass defaults to `max_regenerations: int = 3`. This creates a discrepancy where the configuration parameter and the code default do not align.

**Current Code Snippet:**
```python
# config/config.py, line 17
MAX_REGENERATIONS = 2

# atbp_complete_pipeline.py, line 62
max_regenerations: int = 3
```

**Impact:**
- Confusion about the actual max regeneration attempts
- If config is read, max_regenerations = 2; if ATBPConfig is used directly, max_regenerations = 3
- Inconsistent behavior between direct usage and config-driven usage
- Evaluation results may differ depending on which setting is used

**Recommended Fix:**
Align config.py and ATBPConfig defaults, or ensure config is always loaded and used.

---

### [BUG #13] Verification Threshold Inconsistency (LOW)
**Severity:** LOW  
**File:** config/config.py, atbp_complete_pipeline.py  
**Line Numbers:** config.py line 15, atbp_complete_pipeline.py line 61

**Description:**  
The config module sets `VERIFICATION_THRESHOLD = 0.75` but `ATBPConfig` defaults to `tau: float = 0.80`. According to the ATBP paper specification (mentioned in the docstring), tau should be 0.80, which is correct in ATBPConfig but contradicted in config.py.

**Current Code Snippet:**
```python
# config/config.py, line 15
VERIFICATION_THRESHOLD = 0.75  # Should be 0.80

# atbp_complete_pipeline.py, line 61
tau: float = 0.80  # Correct per ATBP spec
```

**Impact:**
- If config.py VERIFICATION_THRESHOLD is used, claims are incorrectly accepted at 75% confidence instead of 80%
- This violates the ATBP specification (tau = 0.80)
- Evaluation results will deviate from the published algorithm
- Reproducibility is compromised if different thresholds are used in different runs

**Recommended Fix:**
Update config.py line 15 to `VERIFICATION_THRESHOLD = 0.80`.

---

### [BUG #14] Incomplete Claim Extraction Fallback May Introduce Artifacts (LOW)
**Severity:** LOW  
**File:** atbp_complete_pipeline.py  
**Line Numbers:** Lines 565-583

**Description:**  
If JSON claim extraction fails, the fallback decomposes the Agent A output line-by-line and assigns sequential dependencies (`deps = [f"c{idx}"] if idx > 0 else []`). This assumes a linear dependency chain, which may not reflect the actual logical structure. Complex multi-branch reasoning will be incorrectly linearized.

**Current Code Snippet:**
```python
# Lines 565-583 (fallback line-by-line decomposition)
if not claims:
    logger.warning("Claim extraction failed. Using fallback line-by-line decomposition.")
    lines = [line.strip() for line in agent_a_output.split("\n") if line.strip()]
    for idx, line in enumerate(lines):
        cid = f"c{idx+1}"
        deps = [f"c{idx}"] if idx > 0 else []  # Linear chain assumed
        claims.append(AtomicClaim(id=cid, text=line, dependencies=deps))
```

**Impact:**
- Claims with multiple prerequisites will be incorrectly represented as linear chains
- Dependency graph will be artificially simplified
- Verification and repair operations may miss actual dependencies
- Results from fallback-mode extraction will not match the ATBP specification
- User is not clearly warned that results may be unreliable

**Recommended Fix:**
Raise a warning or exception instead of silently applying a lossy fallback. Alternatively, implement a more sophisticated fallback that attempts to infer multi-branch dependencies.

---

## SUMMARY TABLE

| # | Bug Title | File | Line(s) | Severity | Type |
|---|-----------|------|---------|----------|------|
| 1 | Inconsistent LLM Client Usage: Dual APIs | agents/*.py vs atbp_complete_pipeline.py | 1 vs 30, 508-531 | HIGH | Architectural |
| 2 | OpenAI API Configuration Mismatch | config.py, atbp_complete_pipeline.py | 8-9, 20-21, 58-60 | CRITICAL | Config Error |
| 3 | Claim Repair Has No Retry Logic | atbp_complete_pipeline.py | 589-605 | HIGH | Logic Error |
| 4 | Branch Repair Has No Fallback | atbp_complete_pipeline.py | 607-670 | HIGH | Logic Error |
| 5 | Token Tracking Can Receive None | atbp_complete_pipeline.py | 519-531 | HIGH | Data Integrity |
| 6 | JSON Parsing Silent Failure | atbp_complete_pipeline.py | 533-549 | HIGH | Error Handling |
| 7 | Answer Extraction Regex Incomplete | atbp_complete_pipeline.py | 808-823 | HIGH | Parsing Error |
| 8 | Metric Calculation Double-Count Issues | atbp_complete_pipeline.py | 981-1009, 1013-1024 | MEDIUM | Computation Error |
| 9 | Hardcoded Prompts Without System Directive | atbp_complete_pipeline.py | 69-188 | MEDIUM | Design Issue |
| 10 | Missing LLM Error Recovery/Retry | atbp_complete_pipeline.py | 519-531 | MEDIUM | Resilience |
| 11 | Claim Repair Convergence / No Escalation | atbp_complete_pipeline.py | 816-835 | MEDIUM | Logic Error |
| 12 | Configuration Parameter Inconsistency | config.py, atbp_complete_pipeline.py | 15, 17 vs 62 | LOW | Config |
| 13 | Verification Threshold Inconsistency | config.py, atbp_complete_pipeline.py | 15 vs 61 | LOW | Config |
| 14 | Incomplete Claim Extraction Fallback | atbp_complete_pipeline.py | 565-583 | LOW | Design Issue |

---

## Blocking Issues (Must Fix Before Running)

**CRITICAL:** Bug #2 (OpenAI API Configuration Mismatch) must be fixed:
- Causes API endpoint mismatch and authentication failures
- Will result in connection refused or API key authentication errors

**HIGH:** Bugs #1 and #3-#7 should be fixed before evaluation runs:
- **#1** creates architectural inconsistency between agents and pipeline (incompatible client interfaces)
- **#3-#7** cause incorrect results, silent data loss, or incomplete recovery logic

**Note on Bug #1:** The `src.llm_client` module DOES exist and imports succeed. However, the dual LLM client architecture (agents use abstracted interface, pipeline uses direct SDK) prevents clean integration. If agents are never called by the pipeline, this is a code smell indicating incomplete integration, not a runtime blocker.

---

## Recommendations

1. **Immediate (Before First Run):**
   - Fix Bug #2 (OpenAI API config) — verify base_url and api_key align with `.env`
   - Fix Bug #1 (Unify LLM client) — either refactor agents to use pipeline's LLMClient or vice versa
   - Fix Bug #6 (JSON parsing) — add logging and error handling for silent failures

2. **Before Evaluation (Before Large-Scale Testing):**
   - Fix Bugs #3, #4, #5, #7 (Retry logic, fallback strategies, token tracking, answer extraction)
   - Implement error recovery (Bug #10) for resilience during long runs
   - Verify metric calculations are correct (Bug #8)

3. **Optimization (Post-Initial Success):**
   - Address Bugs #9, #12-#14 (Prompts, config consistency, fallback robustness)
   - Consider unified system prompt (Bug #9) for consistency across all LLM calls

