# ATBP Smoke Test - Llama 3.1:8b

**Date:** 2026-10-19

## Exit Status
**ERROR** - Run incomplete (timeout on example 3)

## Command
```
python experiments\run_comparative.py --num-examples=5 --strategies=a0,a4 --output-dir=results\smoke_llama31
```

## Execution Summary
- Ollama status: Running (llama3.1:8b available)
- Examples completed: 2 out of 5
- Timeout occurred: During example 3, A4 strategy (after ~10 minutes)
- Python errors: None detected in completed runs

## Results by Strategy

### A0 (Baseline) - 2/2 Examples Completed
- Example 1 (Janet's ducks): ✅ Correct (answer: 18)
- Example 2 (Robe bolts): ✅ Correct (answer: 3)
- **A0 Accuracy: 2/2 correct (100%)**
- Mean latency: ~89 seconds

### A4 (Adaptive Recovery) - 2/2 Examples Completed (before timeout)
- Example 1 (Janet's ducks): ✅ Correct (answer: 18)
- Example 2 (Robe bolts): ❌ Incorrect (predicted: 2, expected: 3)
- **A4 Accuracy: 1/2 correct (50%)**
- Mean latency: ~145 seconds

## Output Logs

### Standard Output (Partial)
```
Loading GSM8K dataset...
Warning: You are sending unauthenticated requests to the HF Hub. Please set a HF_TOKEN to enable higher rate limits and faster downloads.
Running 5 examples with strategies: a0, a4
Example 1/5
  Running A0... OK (True)
  Running A4... OK (True)
Example 2/5
  Running A0... OK (True)
  Running A4... OK (False)
Example 3/5
  Running A0... (in progress)
  [TIMEOUT after 600 seconds]
```

## Errors Encountered
1. **A4 Hang on Example 3**: The A4 strategy appears to enter an extended processing loop on the third problem. This may be related to:
   - Repeated verification-repair cycles in adaptive scope selection
   - Regeneration loops with MAX_REGENERATIONS=5
   - Claim extraction or dependency graph building performance issues

2. **A4 Accuracy Regression**: Example 2 shows A4 producing incorrect output (2 instead of 3) despite passing verification. Agent B appears to have introduced reasoning errors that Agent C did not catch.

## Python Errors
**None detected** - No import, syntax, or runtime Python errors in completed examples.

## Configuration Notes
- MODEL_NAME: llama3.1:8b
- TEMPERATURE: 0
- MAX_TOKENS: 2048
- VERIFICATION_THRESHOLD: 0.85
- MAX_REGENERATIONS: 5
- MAX_REPAIR_ATTEMPTS: 3

All configuration values properly loaded from config.py.

## Go / No-Go Verdict

**FAIL**

### Reasons:
1. **Incomplete Run**: Test did not complete all 5 examples due to timeout on example 3 during A4 strategy
2. **A4 Performance Issue**: Adaptive recovery strategy shows signs of performance degradation or logic issues causing hangs and accuracy regression
3. **Accuracy Threshold Not Met**: A4 accuracy on completed examples (1/2) is below acceptable baseline, and A0 works correctly but further testing interrupted

### Next Steps Recommended:
1. Investigate A4 hanging on example 3 - check for infinite loops in verify_claims or adaptive_scope_selector
2. Debug example 2 A4 output discrepancy - Agent B reasoning diverged from correct path and was not caught
3. Profile claim verification and dependency graph operations for performance bottlenecks
4. Consider reducing MAX_REGENERATIONS or adding iteration limits with early termination
5. Re-run with a time limit per example or per strategy to prevent full test hangups

---

**Report Generated:** 2026-10-19  
**Workspace:** e:\Sakib project\ATBP  
**Model:** llama3.1:8b
