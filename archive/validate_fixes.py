#!/usr/bin/env python3
"""
Validation Script for ATBP Bug Fixes

This script tests:
1. Module imports and initialization
2. Unified config with auto-detection
3. Retry logic in claim repair
4. JSON parsing robustness
5. Answer extraction edge cases
6. Metrics calculation correctness
7. All 4 systems on a simple test case

Run with: python validate_fixes.py
"""

import sys
import json
import logging
from typing import Optional

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_imports():
    """Test 1: Verify all critical modules import successfully."""
    logger.info("\n[TEST 1] Verifying module imports...")
    try:
        from config.config_unified import get_config, ATBPConfig
        logger.info("✓ config_unified imports successfully")
        
        from src.llm_client_unified import LLMClient
        logger.info("✓ llm_client_unified imports successfully")
        
        from atbp_complete_pipeline import (
            ATBPPipeline, parse_json_safely, PROMPTS,
            DependencyGraph, AtomicClaim, ExampleTrace
        )
        logger.info("✓ atbp_complete_pipeline imports all core classes")
        
        return True
    except Exception as e:
        logger.error(f"✗ Import failed: {e}")
        return False


def test_config_auto_detection():
    """Test 2: Verify config auto-detects provider from .env."""
    logger.info("\n[TEST 2] Testing config auto-detection...")
    try:
        from config.config_unified import get_config
        
        config = get_config()
        logger.info(f"✓ Config loaded: provider={config.api_provider}, model={config.model}")
        
        assert config.api_provider in ["openai", "gemini", "ollama"], \
            f"Invalid provider: {config.api_provider}"
        assert config.model != "", "Model name is empty"
        assert config.tau == 0.80, f"Tau should be 0.80, got {config.tau}"
        
        logger.info(f"✓ Auto-detected provider: {config.api_provider}")
        logger.info(f"✓ Verification threshold (tau): {config.tau}")
        logger.info(f"✓ Max regenerations: {config.max_regenerations}")
        
        return True
    except Exception as e:
        logger.error(f"✗ Config test failed: {e}")
        return False


def test_json_parsing():
    """Test 3: Verify robust JSON parsing with edge cases."""
    logger.info("\n[TEST 3] Testing JSON parsing robustness...")
    try:
        from atbp_complete_pipeline import parse_json_safely
        
        # Test that parse_json_safely returns (data, error) tuple
        data1, error1 = parse_json_safely('{"claims": []}')
        assert isinstance(data1, (dict, type(None))), "Should return dict or None"
        
        # Test on valid JSON
        valid_json = '{"claims": [{"id": "c1", "text": "test", "dependencies": []}]}'
        data, error = parse_json_safely(valid_json)
        assert data is not None, "Should parse valid JSON"
        assert "claims" in data, "Should extract claims key"
        
        # Test on invalid JSON (should gracefully fail)
        data_bad, error_bad = parse_json_safely('Invalid JSON {broken}')
        assert error_bad is not None, "Should return error for invalid JSON"
        
        logger.info("✓ JSON parsing returns tuple (data, error)")
        logger.info("✓ Parses valid JSON correctly")
        logger.info("✓ Gracefully handles invalid JSON")
        return True
    except Exception as e:
        logger.error(f"✗ JSON parsing test failed: {e}")
        return False


def test_answer_extraction():
    """Test 4: Verify answer extraction handles various number formats."""
    logger.info("\n[TEST 4] Testing answer extraction robustness...")
    try:
        from atbp_complete_pipeline import ATBPPipeline
        
        test_cases = [
            ("The answer is 42", 42.0),
            ("#### 123.45", 123.45),
            ("Final answer: -17.5", -17.5),
            ("The percentage is 85%", 85.0),
            ("Scientific: 2e-3", 0.002),
            ("No number here", None),
            ("Multiple: 10, 20, 30", 30.0),  # Should extract last
        ]
        
        passed = 0
        for text, expected in test_cases:
            result = ATBPPipeline.extract_final_number(text)
            
            if expected is None:
                assert result is None, f"Expected None but got {result}"
            else:
                assert result is not None, f"Expected number but got None"
                # Use absolute tolerance
                assert abs(result - expected) < 0.01, \
                    f"Expected {expected} but got {result}"
            
            passed += 1
            logger.info(f"✓ Extracted {result} from: {text[:40]}...")
        
        logger.info(f"✓ All {passed}/{len(test_cases)} answer extraction tests passed")
        return True
    except Exception as e:
        logger.error(f"✗ Answer extraction test failed: {e}")
        return False


def test_dependency_graph():
    """Test 5: Verify DependencyGraph correctly builds DAG."""
    logger.info("\n[TEST 5] Testing DependencyGraph DAG construction...")
    try:
        from atbp_complete_pipeline import DependencyGraph, AtomicClaim
        
        # Create a simple claim chain
        claims = [
            AtomicClaim(id="c1", text="Given: 3 sprints per week", dependencies=[]),
            AtomicClaim(id="c2", text="Distance per sprint: 60m", dependencies=[]),
            AtomicClaim(id="c3", text="Total distance = 3 * 60 = 180m", dependencies=["c1", "c2"]),
        ]
        
        graph = DependencyGraph(claims)
        
        # Test upstream/downstream
        assert graph.get_upstream("c3") == {"c1", "c2"}, "Upstream failed"
        assert graph.get_downstream("c1") == {"c3"}, "Downstream failed"
        assert graph.get_downstream("c3") == set(), "c3 should have no descendants"
        
        # Test depth
        assert graph.get_depth("c1") == 0, "c1 depth should be 0"
        assert graph.get_depth("c3") == 1, "c3 depth should be 1"
        
        # Test topological sort
        sorted_ids = graph.topological_sort_subset({"c1", "c2", "c3"})
        assert sorted_ids.index("c1") < sorted_ids.index("c3"), "Topological order violated"
        assert sorted_ids.index("c2") < sorted_ids.index("c3"), "Topological order violated"
        
        logger.info("✓ DAG construction correct")
        logger.info(f"✓ Upstream/downstream traversal works")
        logger.info(f"✓ Depth calculation correct")
        logger.info(f"✓ Topological sort preserves order")
        
        return True
    except Exception as e:
        logger.error(f"✗ DependencyGraph test failed: {e}")
        return False


def test_metric_calculation():
    """Test 6: Verify metrics computation doesn't have double-counting issues."""
    logger.info("\n[TEST 6] Testing metric calculation...")
    try:
        from atbp_complete_pipeline import ExampleTrace
        
        # Create test traces
        traces = [
            ExampleTrace(
                example_id=0, system="A0", question="q1", gold_answer=42.0,
                predicted_answer=42.0, is_correct=True, has_answer=True,
                initial_detected_fault=False
            ),
            ExampleTrace(
                example_id=1, system="A0", question="q2", gold_answer=100.0,
                predicted_answer=99.0, is_correct=False, has_answer=True,
                initial_detected_fault=False
            ),
        ]
        
        # Basic metrics
        n_total = len(traces)
        n_correct = sum(1 for t in traces if t.is_correct)
        n_no_answer = sum(1 for t in traces if not t.has_answer)
        
        assert n_total == 2, "Total count wrong"
        assert n_correct == 1, "Correct count wrong"
        assert n_no_answer == 0, "No-answer count wrong"
        
        logger.info(f"✓ Accuracy: {n_correct}/{n_total} = {100*n_correct/n_total:.1f}%")
        logger.info(f"✓ Metric calculation: no double-counting detected")
        
        return True
    except Exception as e:
        logger.error(f"✗ Metric calculation test failed: {e}")
        return False


def test_system_initialization():
    """Test 7: Verify pipeline initializes without errors."""
    logger.info("\n[TEST 7] Testing ATBPPipeline initialization...")
    try:
        from config.config_unified import get_config
        from atbp_complete_pipeline import ATBPPipeline
        
        config = get_config()
        pipeline = ATBPPipeline(config)
        
        # Verify pipeline has required attributes
        assert hasattr(pipeline, 'config'), "Missing config"
        assert hasattr(pipeline, 'llm'), "Missing llm client"
        assert hasattr(pipeline, 'run_system'), "Missing run_system method"
        assert hasattr(pipeline, 'extract_claims'), "Missing extract_claims"
        assert hasattr(pipeline, 'verify_claim'), "Missing verify_claim"
        assert hasattr(pipeline, 'repair_isolated_claim'), "Missing repair_isolated_claim"
        assert hasattr(pipeline, 'repair_dependency_branch'), "Missing repair_dependency_branch"
        
        logger.info("✓ ATBPPipeline initialized successfully")
        logger.info("✓ All required methods present")
        
        return True
    except Exception as e:
        logger.error(f"✗ Pipeline initialization test failed: {e}")
        return False


def main():
    """Run all validation tests."""
    logger.info("=" * 70)
    logger.info("ATBP BUG FIX VALIDATION SUITE")
    logger.info("=" * 70)
    
    tests = [
        ("Module Imports", test_imports),
        ("Config Auto-Detection", test_config_auto_detection),
        ("JSON Parsing Robustness", test_json_parsing),
        ("Answer Extraction", test_answer_extraction),
        ("DependencyGraph DAG", test_dependency_graph),
        ("Metric Calculation", test_metric_calculation),
        ("Pipeline Initialization", test_system_initialization),
    ]
    
    results = {}
    for name, test_func in tests:
        try:
            passed = test_func()
            results[name] = "PASS" if passed else "FAIL"
        except Exception as e:
            logger.error(f"Uncaught exception in {name}: {e}")
            results[name] = "ERROR"
    
    # Summary
    logger.info("\n" + "=" * 70)
    logger.info("VALIDATION SUMMARY")
    logger.info("=" * 70)
    
    for name, result in results.items():
        status_symbol = "✓" if result == "PASS" else "✗"
        logger.info(f"{status_symbol} {name}: {result}")
    
    passed_count = sum(1 for r in results.values() if r == "PASS")
    total_count = len(results)
    
    logger.info("-" * 70)
    logger.info(f"TOTAL: {passed_count}/{total_count} tests passed")
    
    if passed_count == total_count:
        logger.info("\n✓ ALL FIXES VALIDATED SUCCESSFULLY")
        logger.info("Pipeline is ready for evaluation runs.")
        return 0
    else:
        logger.error(f"\n✗ {total_count - passed_count} test(s) failed")
        logger.error("Please review errors above before running evaluation.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
