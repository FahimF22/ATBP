# Running ATBP Evaluation

This guide walks you through validating and running the ATBP evaluation pipeline.

---

## Prerequisites

### 1. Python Environment

Ensure you have Python 3.8+ with required dependencies:

```bash
pip install python-dotenv openai google-generativeai datasets
```

Or use the existing requirements.txt:

```bash
pip install -r requirements.txt
```

### 2. Configure API Keys

The system auto-detects your LLM provider from `.env`. Ensure one of these is set:

**Option A: Using OpenAI (Recommended)**
```
.env file should contain:
OPENAI_API_KEY=sk-...
```

**Option B: Using Google Gemini**
```
.env file should contain:
GEMINI_API_KEY=AI...
```

**Option C: Using Local Ollama**
```
No API key needed. Ensure Ollama is running:
ollama serve llama3.2:latest
```

Current `.env` status:
```
✓ OPENAI_API_KEY is set (OpenAI will be used)
✓ GEMINI_API_KEY is set (fallback if OpenAI unavailable)
```

---

## Step 1: Validate Fixes

Before running evaluation, validate that all bug fixes are working:

```bash
python validate_fixes.py
```

**Expected output:**
```
✓ Module Imports: PASS
✓ Config Auto-Detection: PASS
✓ JSON Parsing Robustness: PASS
✓ Answer Extraction: PASS
✓ DependencyGraph DAG: PASS
✓ Metric Calculation: PASS
✓ Pipeline Initialization: PASS

TOTAL: 7/7 tests passed
✓ ALL FIXES VALIDATED SUCCESSFULLY
```

If any test fails, review the error and check `FIXES_SUMMARY.md` for details.

---

## Step 2: Run Small Test (5 Examples)

Test the pipeline with a small sample to verify everything works:

```bash
python atbp_complete_pipeline.py --num_examples 5 --systems A0,A2,A3,A4
```

**What this does:**
- Loads 5 GSM8K examples
- Runs all 4 systems (A0, A2, A3, A4)
- Produces `atbp_results_5.json` with results
- Takes ~2-5 minutes depending on your LLM provider

**Expected output:**
```
INFO - Loaded 5 GSM8K examples. Running systems ['A0', 'A2', 'A3', 'A4'] with model 'gpt-4o-mini'...

--- Example 0 (Gold: 18.0) ---
Question: Janet's ducks lay 16 eggs per day...

[A0] Pred: 18.0 | Correct: True | Fault: False | Attempts: 0 | Latency: 12.3s | Tokens: 1250
[A2] Pred: 18.0 | Correct: True | Fault: False | Attempts: 0 | Latency: 11.8s | Tokens: 1200
[A3] Pred: 18.0 | Correct: True | Fault: False | Attempts: 0 | Latency: 11.5s | Tokens: 1180
[A4] Pred: 18.0 | Correct: True | Fault: False | Attempts: 0 | Latency: 11.2s | Tokens: 1150

...

================ FINAL SUMMARY TABLE ================
System | Correct | Acc(%)  | 95% CI      | NoAns | ECR        | RSR        | CDR        | Latency(s) | Rel.Lat | AvgTokens
A0     | 5/5     | 100.0   | [47.8, 100.0] | 0  | n/a        | n/a        | n/a        | 11.2      | 1.00x   | 1200

Saved full experiment logs and metrics to atbp_results_5.json
```

---

## Step 3: Run Full Evaluation (100 Examples)

Once the 5-example test succeeds, run the full evaluation:

```bash
python atbp_complete_pipeline.py --num_examples 100 --systems A0,A2,A3,A4
```

**Execution time:**
- With OpenAI GPT-4o-mini: ~30-60 minutes (depending on rate limits)
- With Gemini: ~45-90 minutes
- With local Ollama: ~2-4 hours

**What this produces:**
- `atbp_results_100.json` — Full experiment logs and metrics
- Console output with FINAL SUMMARY TABLE (metrics for all 4 systems)

---

## Understanding Results

### Output Format

The main output file `atbp_results_100.json` contains:

```json
{
  "config": {
    "api_provider": "openai",
    "model": "gpt-4o-mini",
    "tau": 0.80,
    "max_regenerations": 3,
    ...
  },
  "summaries": [
    {
      "system": "A0",
      "correct": "82/100",
      "acc_pct": 82.0,
      "wilson_95_ci": "[71.8, 89.2]",
      "ECR": "15.2% (13/85)",
      "RSR": "n/a",
      "CDR": "n/a",
      ...
    },
    ...
  ],
  "traces": {
    "A0": [ /* 100 per-example traces */ ],
    "A2": [ /* 100 per-example traces */ ],
    ...
  }
}
```

### Key Metrics

**Accuracy (Acc%)**
- Percentage of examples where final predicted answer matches gold answer
- Reported with 95% Wilson confidence interval

**Error Cascade Rate (ECR)**
- % of examples with detected intermediate faults whose final answer is incorrect
- Shows if faults cascade to final answer

**Repair Success Rate (RSR)**
- % of repair attempts that succeeded on re-verification
- Higher is better (shows repair strategy efficacy)

**Collateral Damage Rate (CDR)**
- % of previously-valid claims altered during recovery
- Lower is better (shows repair strategy targeted-ness)

### Interpreting Results

**Expected Ranking (A0 vs A2 vs A3 vs A4):**

```
Accuracy:        A4 ≥ A3 ≥ A2 > A0
                (adaptive > fixed-isolated > full-regen > no-recovery)

RSR:             A3, A4 > A2
                (both use targeted repair, higher success rate)

CDR:             A3 ≤ A4 << A2
                (A3 never alters verified claims, A2 replaces everything)

Latency:         A4 < A3 < A2 < A0
                (overhead decreases in this order)
```

---

## Advanced Usage

### Run Specific Systems Only

```bash
# Test only A0 and A4 (skip A2, A3)
python atbp_complete_pipeline.py --num_examples 100 --systems A0,A4

# Test only A2
python atbp_complete_pipeline.py --num_examples 100 --systems A2
```

### Custom Configuration

```bash
# Use custom verification threshold
python atbp_complete_pipeline.py --num_examples 20 --tau 0.75

# Use local Ollama (fallback if no API keys)
# (Auto-detection will use Ollama if no API keys are set)
python atbp_complete_pipeline.py --num_examples 10

# Specify local GSM8K file (if you have one)
python atbp_complete_pipeline.py --num_examples 100 --data_path ~/gsm8k_test.jsonl
```

### Output to Custom File

```bash
python atbp_complete_pipeline.py --num_examples 100 --output_file my_results.json
```

---

## Troubleshooting

### Issue: "OpenAI API Error: 401 Unauthorized"
**Solution:** Check `.env` file for valid `OPENAI_API_KEY`
```bash
cat .env | grep OPENAI_API_KEY
```

### Issue: "ModuleNotFoundError: No module named 'config.config_unified'"
**Solution:** Ensure you're running from the project root:
```bash
cd /path/to/ATBP
python atbp_complete_pipeline.py ...
```

### Issue: "Connection refused" (Ollama)
**Solution:** If using Ollama, start the server:
```bash
ollama serve llama3.2:latest
```

### Issue: "Rate limit exceeded" (OpenAI)
**Solution:** 
- Pause between runs (OpenAI has rate limits)
- Consider using Gemini as fallback
- Reduce `--num_examples` for testing

### Issue: Slow performance
**Solution:**
- Start with smaller batches (`--num_examples 10`)
- Check your internet connection
- Consider switching to a faster LLM provider

---

## File Structure

```
ATBP/
├── atbp_complete_pipeline.py    # Main pipeline (FIXED)
├── config/
│   ├── config.py                # Legacy config (kept for reference)
│   └── config_unified.py        # NEW: Unified config with auto-detection
├── src/
│   ├── llm_client.py            # Legacy client (kept for reference)
│   └── llm_client_unified.py    # NEW: Unified LLM client
├── agents/                       # Legacy agent modules (not used)
├── validate_fixes.py            # NEW: Validation suite
├── AUDIT_REPORT.md              # Bug audit report
├── FIXES_SUMMARY.md             # This summary of all fixes
├── RUN_EVALUATION.md            # This guide
├── requirements.txt             # Python dependencies
├── .env                         # API keys (auto-loaded)
└── results/                     # Output directory
    ├── atbp_results_5.json      # 5-example test results
    ├── atbp_results_100.json    # 100-example full results
    └── ...
```

---

## Next Steps After Evaluation

1. **Analyze Results:**
   - Review the FINAL SUMMARY TABLE in console output
   - Open `atbp_results_100.json` in editor or Python
   - Plot accuracy, ECR, RSR, CDR across all 4 systems

2. **Generate Paper-Ready Tables:**
   ```bash
   # (Script to be written, or analyze manually)
   # Convert JSON to LaTeX tables for publication
   ```

3. **Identify Improvements:**
   - Check which system performs best overall
   - Look for patterns in failure modes
   - Consider tuning π(x_f) thresholds if needed

4. **Optional: Further Optimization:**
   - Fine-tune recovery policy thresholds
   - Add new claim verification strategies
   - Test on other benchmarks (MATH, AQuA, etc.)

---

## Support

For issues or questions:
1. Check `AUDIT_REPORT.md` for technical details
2. Review `FIXES_SUMMARY.md` for fix descriptions
3. Consult inline comments in `atbp_complete_pipeline.py`

---

**Last Updated:** October 20, 2024  
**Status:** ✅ Ready for Evaluation
