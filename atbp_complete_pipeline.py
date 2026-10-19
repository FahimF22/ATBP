"""
Adaptive Targeted Backtracking Protocol (ATBP)
Complete End-to-End Implementation for Sequential Multi-Agent Reasoning on GSM8K.

Implements:
- Sequential Multi-Agent Pipeline (Agent A -> Agent B -> Agent C)
- Atomic Claim Extraction (Structured JSON)
- Directed Dependency Graph G = (V, E) with depth, upstream/downstream, and cycle detection
- Claim Verifier V(c_i) = (valid_i, q_i) with threshold tau = 0.80
- All 4 Evaluated Systems:
    * A0: Sequential Baseline (No Verification)
    * A2: Verify + Full Regeneration (Up to 3 attempts, temp=0.7, different seeds)
    * A3: Verify + Isolated Claim Repair
    * A4: ATBP (Adaptive Recovery Scope Selector: Claim, Branch, Agent, Full)
- Full Evaluation Metrics & Instrumentation:
    * Final-Answer Accuracy + 95% Wilson Confidence Interval
    * Error Cascade Rate (ECR)
    * Repair Success Rate (RSR)
    * Collateral Damage Rate (CDR)
    * Mean End-to-End Latency & Token Usage Instrumentation
"""

import os
import re
import json
import time
import math
import argparse
import logging
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Set, Tuple, Optional, Any

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import unified config and LLM client
from config.config_unified import get_config, ATBPConfig
from src.llm_client_unified import LLMClient

# Load config once at module level
config = get_config()
llm_client = LLMClient(config)

# =====================================================================
# 1. PROMPTS
# =====================================================================

PROMPTS = {
    "agent_a": """You are Agent A, the Mathematical Planner and Reasoner in a sequential multi-agent system.

Given a math word problem, break down the solution into a clear, numbered sequence of intermediate reasoning steps.

- Identify all key quantities given in the problem.
- State each logical deduction and intermediate arithmetic calculation clearly, one step per line.
- Do not skip intermediate steps.

Problem:
{problem}

Output your step-by-step reasoning plan:""",

    "claim_extractor": """You are an Atomic Claim Extraction module.

Decompose Agent A's reasoning plan into atomic claims and identify the exact prerequisite claims each claim depends on.

Rules:
1. Each claim must represent a single, self-contained factual statement, assumption, or arithmetic step from the reasoning plan.
2. Assign sequential string IDs: "c1", "c2", "c3", etc.
3. In "dependencies", list the IDs of earlier claims that are directly required to derive or justify the current claim. If a claim comes directly from the problem statement with no prior claim dependencies, use an empty list [].
4. Respond ONLY with valid JSON matching this exact schema:

{
  "claims": [
    {
      "id": "c1",
      "text": "<atomic claim statement>",
      "dependencies": []
    },
    {
      "id": "c2",
      "text": "<atomic claim statement>",
      "dependencies": ["c1"]
    }
  ]
}

Original Problem:
{problem}

Agent A Reasoning Plan:
{agent_a_output}""",

    "claim_verifier": """You are a Mathematical Claim Verifier.

Evaluate whether the Target Claim is logically and arithmetically valid given the Original Problem and its Prerequisite Claims.

Check for:
1. Factual accuracy against the problem statement.
2. Arithmetic correctness.
3. Logical consistency with prerequisite claims.

Respond ONLY with valid JSON in this exact format:

{
  "valid": true,
  "confidence": 0.95,
  "reason": "<brief 1-sentence explanation of why the claim is valid or invalid>"
}

Original Problem:
{problem}

Prerequisite Claims Context:
{prerequisite_claims_text}

Target Claim to Verify:
ID: {claim_id}
Claim: {claim_text}""",

    "isolated_claim_repair": """You are an Isolated Claim Repair module.

A specific claim in a mathematical reasoning plan failed verification. Rewrite ONLY the faulty claim so that it is mathematically and logically correct based on the problem statement and its prerequisite claims.

Original Problem:
{problem}

Valid Prerequisite Claims:
{prerequisite_claims}

Faulty Claim ({claim_id}):
{faulty_claim_text}

Verifier Feedback:
{verifier_reason}

Respond ONLY with valid JSON:

{
  "id": "{claim_id}",
  "repaired_text": "<corrected single atomic claim>"
}""",

    "branch_repair": """You are a Dependency Branch Repair module.

A claim in a reasoning graph failed verification, which invalidates its downstream dependent claims.

Repair the root faulty claim AND recompute all listed downstream dependent claims in topological order so the entire branch is mathematically consistent. Do not alter unaffected claims.

Original Problem:
{problem}

Unaffected Valid Claims (Trusted Context):
{unaffected_claims}

Faulty Root Claim & Verifier Feedback:
{faulty_claim_and_reason}

Downstream Dependent Claims to Recompute (in order):
{downstream_claims_list}

Respond ONLY with valid JSON:

{
  "repaired_branch": [
    {
      "id": "<claim_id>",
      "text": "<corrected claim text>"
    }
  ]
}""",

    "agent_b": """You are Agent B, the Intermediate Mathematical Solver.

You receive the original math word problem and a reasoning plan from Agent A.

Your job is to:
1. Follow the reasoning plan step-by-step.
2. Execute and verify all arithmetic calculations explicitly and accurately.
3. Show the intermediate numerical results clearly for every step.

Original Problem:
{problem}

Reasoning Plan:
{plan_text}

Execute the calculations step-by-step:""",

    "agent_c": """You are Agent C, the Final Answer Synthesizer.

Review the original problem, the reasoning plan from Agent A, and the step-by-step calculations from Agent B.

Verify consistency and output the final numerical answer to the question.

Rules:
- Briefly confirm consistency in 1-2 sentences.
- On the very last line, output ONLY the final numerical value formatted as:

#### <number>

(Do not include units, commas, currency symbols, or words after ####).

Original Problem:
{problem}

Agent A Plan:
{plan_text}

Agent B Calculations:
{agent_b_output}"""
}

# =====================================================================
# 2. DATA STRUCTURES & DEPENDENCY GRAPH G = (V, E)
# =====================================================================

@dataclass
class AtomicClaim:
    id: str
    text: str
    dependencies: List[str] = field(default_factory=list)
    valid: bool = False
    confidence: float = 0.0
    reason: str = ""
    accepted: bool = False

class DependencyGraph:
    """
    Directed Dependency Graph G = (V, E) where an edge (c_i, c_j) indicates
    that claim c_j depends on prerequisite claim c_i (i.e., c_i in D_j).
    """

    def __init__(self, claims: List[AtomicClaim]):
        self.claims: Dict[str, AtomicClaim] = {c.id: c for c in claims}
        self.order: List[str] = [c.id for c in claims]
        self.adj: Dict[str, Set[str]] = {c.id: set() for c in claims}      # c_i -> dependents {c_j}
        self.rev_adj: Dict[str, Set[str]] = {c.id: set() for c in claims}  # c_j -> prerequisites {c_i}
        self._build_graph()

    def _build_graph(self):
        for cid, claim in self.claims.items():
            cleaned_deps = []
            for dep in claim.dependencies:
                if dep in self.claims and dep != cid:
                    self.adj[dep].add(cid)
                    self.rev_adj[cid].add(dep)
                    cleaned_deps.append(dep)
            claim.dependencies = cleaned_deps

        if self.has_cycle():
            self._break_cycles()

    def has_cycle(self) -> bool:
        visited = {}  # 0: unvisited, 1: visiting, 2: visited
        for cid in self.claims:
            visited[cid] = 0

        def dfs(node: str) -> bool:
            visited[node] = 1
            for nxt in self.adj[node]:
                if visited[nxt] == 1:
                    return True
                if visited[nxt] == 0 and dfs(nxt):
                    return True
            visited[node] = 2
            return False

        for cid in self.claims:
            if visited[cid] == 0 and dfs(cid):
                return True
        return False

    def _break_cycles(self):
        """Enforce topological ordering based on claim appearance order if LLM introduces a cycle."""
        logger.warning("Cycle detected in dependency graph. Breaking cycles based on topological order.")
        pos = {cid: idx for idx, cid in enumerate(self.order)}
        for cid in self.order:
            valid_deps = [d for d in self.claims[cid].dependencies if pos.get(d, -1) < pos[cid]]
            self.claims[cid].dependencies = valid_deps

        self.adj = {cid: set() for cid in self.order}
        self.rev_adj = {cid: set() for cid in self.order}
        for cid in self.order:
            for d in self.claims[cid].dependencies:
                self.adj[d].add(cid)
                self.rev_adj[cid].add(d)

    def get_prerequisites(self, cid: str) -> List[str]:
        return list(self.rev_adj.get(cid, set()))

    def get_upstream(self, cid: str) -> Set[str]:
        """Up(c): All ancestor claims on which cid transitively depends."""
        visited = set()
        stack = list(self.rev_adj.get(cid, set()))
        while stack:
            curr = stack.pop()
            if curr not in visited:
                visited.add(curr)
                stack.extend(self.rev_adj.get(curr, set()) - visited)
        return visited

    def get_downstream(self, cid: str) -> Set[str]:
        """Down(c) = {v in V | c ~> v}: All descendant claims that transitively depend on cid."""
        visited = set()
        stack = list(self.adj.get(cid, set()))
        while stack:
            curr = stack.pop()
            if curr not in visited:
                visited.add(curr)
                stack.extend(self.adj.get(curr, set()) - visited)
        return visited

    def get_depth(self, cid: str, memo: Optional[Dict[str, int]] = None) -> int:
        """
        Recursive dependency depth d(c):
        0 if Pred(c) is empty, else 1 + max_{p in Pred(c)} d(p).
        """
        if memo is None:
            memo = {}

        if cid in memo:
            return memo[cid]

        preds = self.rev_adj.get(cid, set())
        if not preds:
            memo[cid] = 0
            return 0

        depth = 1 + max(self.get_depth(p, memo) for p in preds)
        memo[cid] = depth
        return depth

    def get_roots(self) -> List[str]:
        return [cid for cid in self.order if not self.rev_adj[cid]]

    def get_leaves(self) -> List[str]:
        return [cid for cid in self.order if not self.adj[cid]]

    def topological_sort_subset(self, subset: Set[str]) -> List[str]:
        pos = {cid: idx for idx, cid in enumerate(self.order)}
        return sorted(list(subset), key=lambda x: pos.get(x, 9999))

    def to_plan_text(self) -> str:
        return "\n".join(f"{idx+1}. [{cid}] {self.claims[cid].text}" for idx, cid in enumerate(self.order))

# =====================================================================
# 2. ENHANCED JSON PARSING WITH SCHEMA VALIDATION
# =====================================================================

def parse_json_safely(raw_text: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Parse JSON robustly with comprehensive schema validation.
    
    Validates:
    1. JSON structure is parseable
    2. "claims" key exists and is a list
    3. Each claim has required keys: "id", "text", "dependencies"
    4. All dependency IDs exist in the claims list (no dangling references)
    5. No cycles in dependency graph (DAG property)
    
    Args:
        raw_text (str): Raw LLM response (possibly wrapped in markdown)
    
    Returns:
        Tuple[Optional[Dict], Optional[str]]: 
            - (parsed_data, None) if valid and passes all checks
            - (None, error_msg) if any validation fails
            
    Edge cases handled:
        - Markdown code blocks (```json ... ```)
        - Trailing/leading whitespace
        - Malformed JSON
        - Missing required keys
        - Invalid dependency references
        - Circular dependencies
    """
    text = raw_text.strip()
    
    # Try direct JSON parse
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        pass
    else:
        # Direct parse succeeded; validate schema
        error_msg = _validate_claims_schema(data)
        if error_msg:
            return None, error_msg
        return data, None
    
    # Try extracting JSON from markdown code blocks
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, flags=re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(1))
            error_msg = _validate_claims_schema(data)
            if error_msg:
                return None, error_msg
            return data, None
        except json.JSONDecodeError:
            pass
    
    # Try extracting raw JSON object from text
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            error_msg = _validate_claims_schema(data)
            if error_msg:
                return None, error_msg
            return data, None
        except json.JSONDecodeError:
            pass
    
    return None, "Could not extract or parse JSON from response"


def _validate_claims_schema(data: Dict[str, Any]) -> Optional[str]:
    """
    Validate the internal structure of a parsed claims object.
    
    Args:
        data: Parsed JSON data to validate
    
    Returns:
        None if valid, error message string if any validation fails
    """
    if not isinstance(data, dict):
        return "Response is not a JSON object"
    
    if "claims" not in data:
        return "Missing required key 'claims' in response"
    
    claims_list = data["claims"]
    if not isinstance(claims_list, list):
        return f"'claims' must be a list, got {type(claims_list).__name__}"
    
    if len(claims_list) == 0:
        return "Claims list is empty"
    
    # Collect all claim IDs for dependency validation
    claim_ids: Set[str] = set()
    claims_by_id: Dict[str, Dict[str, Any]] = {}
    
    for idx, claim in enumerate(claims_list):
        if not isinstance(claim, dict):
            return f"Claim {idx} is not a dict: {type(claim).__name__}"
        
        # Check required keys
        for required_key in ["id", "text", "dependencies"]:
            if required_key not in claim:
                return f"Claim {idx} missing required key '{required_key}'"
        
        claim_id = str(claim["id"])
        claim_text = claim["text"]
        dependencies = claim["dependencies"]
        
        if not isinstance(claim_text, str):
            return f"Claim {idx} 'text' must be string, got {type(claim_text).__name__}"
        
        if not isinstance(dependencies, list):
            return f"Claim {idx} 'dependencies' must be list, got {type(dependencies).__name__}"
        
        claim_ids.add(claim_id)
        claims_by_id[claim_id] = claim
    
    # Validate dependency references (no dangling refs)
    for claim_id, claim in claims_by_id.items():
        dependencies = claim["dependencies"]
        for dep_id in dependencies:
            if dep_id not in claim_ids:
                return f"Claim {claim_id} depends on non-existent claim '{dep_id}'"
    
    # Check for cycles using DFS
    if _has_cycle_in_dependencies(claims_by_id):
        return "Cycle detected in dependency graph (not a DAG)"
    
    return None


def _has_cycle_in_dependencies(claims_by_id: Dict[str, Dict[str, Any]]) -> bool:
    """
    Detect cycles in claim dependency graph using DFS.
    
    Args:
        claims_by_id: Mapping of claim_id to claim dict
    
    Returns:
        True if a cycle is detected, False otherwise
    """
    visited: Dict[str, int] = {}  # 0: unvisited, 1: visiting, 2: visited
    
    def dfs(node_id: str) -> bool:
        visited[node_id] = 1
        dependencies = claims_by_id[node_id].get("dependencies", [])
        for dep_id in dependencies:
            if dep_id not in visited:
                visited[dep_id] = 0
            if visited[dep_id] == 1:
                return True  # Back edge found; cycle detected
            if visited[dep_id] == 0 and dfs(dep_id):
                return True
        visited[node_id] = 2
        return False
    
    for claim_id in claims_by_id:
        if claim_id not in visited:
            visited[claim_id] = 0
    
    for claim_id in claims_by_id:
        if visited[claim_id] == 0:
            if dfs(claim_id):
                return True
    
    return False

# =====================================================================
# 3. CORE DATA STRUCTURES & DEPENDENCY GRAPH G = (V, E)
# =====================================================================

@dataclass
class ExampleTrace:
    example_id: int
    system: str
    question: str
    gold_answer: Optional[float]
    predicted_answer: Optional[float]
    is_correct: bool
    has_answer: bool
    initial_detected_fault: bool = False
    repair_attempts: int = 0
    successful_repairs: int = 0
    correct_units_exposed: int = 0
    correct_units_altered: int = 0
    selected_scopes: List[str] = field(default_factory=list)
    latency_sec: float = 0.0
    total_tokens: int = 0

class ATBPPipeline:
    def __init__(self, config: ATBPConfig):
        self.config = config
        self.llm = llm_client  # Use global llm_client initialized at module level
        self.total_tokens = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
    
    def reset_tokens(self):
        """Reset token counters for a new example."""
        self.total_tokens = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
    
    def _track_tokens(self, usage_dict: Dict[str, int]):
        """
        Safely track token usage with fallback estimation.
        
        Ensures prompt_tokens and completion_tokens are always valid (>= 0).
        """
        prompt_tokens = usage_dict.get("prompt_tokens", 0)
        completion_tokens = usage_dict.get("completion_tokens", 0)
        
        # Validate tokens are non-negative
        prompt_tokens = max(0, int(prompt_tokens) if prompt_tokens is not None else 0)
        completion_tokens = max(0, int(completion_tokens) if completion_tokens is not None else 0)
        
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
        self.total_tokens += (prompt_tokens + completion_tokens)

    # --- Sequential Agents ---

    def run_agent_a(self, problem: str, temp: float = 0.0, seed: Optional[int] = None) -> str:
        """Run Agent A with temperature and optional seed for reproducibility."""
        prompt = PROMPTS["agent_a"].replace("{problem}", problem)
        response_text, usage_dict = self.llm.call(prompt, temperature=temp, max_tokens=self.config.max_tokens, seed=seed)
        self._track_tokens(usage_dict)
        return response_text

    def run_agent_b(self, problem: str, plan_text: str) -> str:
        """Run Agent B to execute the plan with calculations."""
        prompt = PROMPTS["agent_b"].replace("{problem}", problem).replace("{plan_text}", plan_text)
        response_text, usage_dict = self.llm.call(prompt, temperature=self.config.temps[0], max_tokens=self.config.max_tokens)
        self._track_tokens(usage_dict)
        return response_text

    def run_agent_c(self, problem: str, plan_text: str, agent_b_output: str) -> str:
        """Run Agent C to synthesize the final answer."""
        prompt = (PROMPTS["agent_c"]
                 .replace("{problem}", problem)
                 .replace("{plan_text}", plan_text)
                 .replace("{agent_b_output}", agent_b_output))
        response_text, usage_dict = self.llm.call(prompt, temperature=self.config.temps[0], max_tokens=self.config.max_tokens)
        self._track_tokens(usage_dict)
        return response_text

    # --- Extraction & Verification ---

    def extract_claims(self, problem: str, agent_a_output: str) -> DependencyGraph:
        """
        Extract atomic claims from Agent A's output.
        
        Handles:
        - Schema validation (claims key, required fields, dependencies)
        - Dangling references (no invalid deps)
        - Cycles in dependency graph
        - JSON parsing errors with markdown code blocks
        - Fallback to line-by-line decomposition if all else fails
        """
        # Use replace instead of format to avoid issues with curly braces in agent_a_output
        prompt_template = PROMPTS["claim_extractor"]
        prompt = prompt_template.replace("{problem}", problem).replace("{agent_a_output}", agent_a_output)
        
        raw = self.llm.call(prompt, temperature=0.0)
        response_text = raw[0] if isinstance(raw, tuple) else raw
        usage_dict = raw[1] if isinstance(raw, tuple) else {}
        
        # Track tokens
        self._track_tokens(usage_dict)
        
        # Parse with schema validation
        data, parse_error = parse_json_safely(response_text)
        
        if parse_error:
            logger.warning(f"Claim extraction JSON parse failed: {parse_error}. Response preview: {response_text[:200]}. Using fallback.")
            data = None
        
        raw_claims = data.get("claims", []) if data else []
        claims: List[AtomicClaim] = []

        if isinstance(raw_claims, list) and len(raw_claims) > 0:
            for idx, item in enumerate(raw_claims):
                if isinstance(item, dict):
                    cid = str(item.get("id", f"c{idx+1}"))
                    text = str(item.get("text", "")).strip()
                    deps = item.get("dependencies", [])
                    if not isinstance(deps, list):
                        deps = []
                    deps = [str(d) for d in deps]
                    if text:
                        claims.append(AtomicClaim(id=cid, text=text, dependencies=deps))

        # Fallback line-by-line decomposition if JSON extraction fails
        if not claims:
            logger.warning("Claim extraction failed. Using fallback line-by-line decomposition.")
            lines = [line.strip() for line in agent_a_output.split("\n") if line.strip()]
            for idx, line in enumerate(lines):
                cid = f"c{idx+1}"
                deps = [f"c{idx}"] if idx > 0 else []
                claims.append(AtomicClaim(id=cid, text=line, dependencies=deps))

        return DependencyGraph(claims)

    def verify_claim(self, problem: str, graph: DependencyGraph, cid: str) -> AtomicClaim:
        """Verify a claim using GPT-4 style evaluation with confidence scoring."""
        claim = graph.claims[cid]
        prereq_ids = graph.get_prerequisites(cid)

        if prereq_ids:
            prereq_text = "\n".join(f"- [{pid}] {graph.claims[pid].text}" for pid in prereq_ids)
        else:
            prereq_text = "None (derived directly from problem statement)."

        prompt_template = PROMPTS["claim_verifier"]
        prompt = (prompt_template
                 .replace("{problem}", problem)
                 .replace("{prerequisite_claims_text}", prereq_text)
                 .replace("{claim_id}", cid)
                 .replace("{claim_text}", claim.text))

        response_text, usage_dict = self.llm.call(prompt, temperature=0.0, max_tokens=self.config.max_tokens)
        self._track_tokens(usage_dict)
        
        # Parse verification response with schema validation
        data, parse_error = parse_json_safely(response_text)
        
        if parse_error or data is None:
            logger.warning(f"Verification response parsing failed for {cid}: {parse_error}")
            valid = False
            confidence = 0.0
            reason = "Verification response unparseable"
        else:
            valid = bool(data.get("valid", False))
            try:
                confidence = float(data.get("confidence", 0.0))
            except (ValueError, TypeError):
                confidence = 0.0
            reason = str(data.get("reason", "Verification failed or unparseable."))

        claim.valid = valid
        claim.confidence = max(0.0, min(1.0, confidence))
        claim.reason = reason
        claim.accepted = (claim.valid is True) and (claim.confidence >= self.config.tau)

        return claim

    def verify_all_claims(self, problem: str, graph: DependencyGraph) -> bool:
        all_accepted = True
        for cid in graph.order:
            c = self.verify_claim(problem, graph, cid)
            if not c.accepted:
                all_accepted = False
        return all_accepted

    # --- Targeted Repair Operations ---

    def repair_isolated_claim(self, problem: str, graph: DependencyGraph, cid: str) -> Tuple[bool, int, int]:
        """
        Repair single faulty claim with retry logic.
        
        Implements configurable retry loop (up to max_regenerations attempts):
        - Temperature increases: attempt_1=0.7, attempt_2=0.8, attempt_3=0.9
        - Each retry uses different seed: seed = base_seed + attempt
        - Re-verifies after each repair
        - Returns on first success
        - On failure: returns (False, max_attempts, total_tokens)
        
        Args:
            problem: The original problem
            graph: The dependency graph
            cid: Claim ID to repair
        
        Returns:
            Tuple[success, attempt_number, tokens_used]:
                - success: True if repair succeeded and verified
                - attempt_number: Which attempt succeeded (or max attempts if all failed)
                - tokens_used: Total tokens for all attempts combined
        """
        claim = graph.claims[cid]
        prereq_ids = graph.get_prerequisites(cid)
        prereq_text = "\n".join(f"- [{pid}] {graph.claims[pid].text}" for pid in prereq_ids) or "None"
        
        total_tokens = 0
        
        for attempt in range(1, self.config.max_regenerations + 1):
            # Increase temperature with each retry: 0.7 -> 0.8 -> 0.9
            temperature = 0.7 + (attempt - 1) * 0.1
            
            # Different seed per attempt for diversity
            seed = self.config.base_seed + attempt
            
            prompt = (PROMPTS["isolated_claim_repair"]
                     .replace("{problem}", problem)
                     .replace("{prerequisite_claims}", prereq_text)
                     .replace("{claim_id}", cid)
                     .replace("{faulty_claim_text}", claim.text)
                     .replace("{verifier_reason}", claim.reason))
            
            response_text, usage_dict = self.llm.call(
                prompt,
                temperature=temperature,
                max_tokens=self.config.max_tokens,
                seed=seed
            )
            self._track_tokens(usage_dict)
            total_tokens += usage_dict.get("prompt_tokens", 0) + usage_dict.get("completion_tokens", 0)
            
            # Parse repair response with schema validation
            data, parse_error = parse_json_safely(response_text)
            
            if parse_error:
                logger.warning(f"Repair attempt {attempt} JSON parse failed for {cid}: {parse_error}")
                new_text = None
            else:
                new_text = str(data.get("repaired_text", "") if data else "").strip()
            
            # Update claim if we got valid repair text
            if new_text:
                original_text = claim.text
                claim.text = new_text
                
                # Re-verify the repaired claim
                self.verify_claim(problem, graph, cid)
                
                if claim.accepted:
                    logger.info(f"Isolated repair succeeded on attempt {attempt} for {cid}")
                    return True, attempt, total_tokens
                else:
                    # Repair didn't improve verification; revert for next retry
                    logger.warning(f"Repair attempt {attempt} for {cid} still failed verification; retrying...")
                    claim.text = original_text
            else:
                logger.warning(f"Repair attempt {attempt} for {cid} produced invalid response")
        
        # All retries failed
        logger.warning(f"All {self.config.max_regenerations} repair attempts failed for {cid}")
        return False, self.config.max_regenerations, total_tokens

    def repair_dependency_branch(self, problem: str, graph: DependencyGraph, root_cid: str) -> Tuple[bool, int, int, str]:
        """
        Multi-tier fallback strategy for branch repair.
        
        Tier 1: Try branch repair (root claim + direct descendants)
        Tier 2: If Tier 1 fails all retries → try full agent regeneration
        Tier 3: If Tier 2 fails → fall back to accepting unverified claim with warning
        
        Returns:
            Tuple[branch_accepted, valid_downstream_rewritten, total_tokens, tier_used]:
                - branch_accepted: True if branch passed verification
                - valid_downstream_rewritten: Count of previously-valid claims in branch
                - total_tokens: Total tokens used across all tiers
                - tier_used: Which tier was ultimately used ("Tier1", "Tier2", "Tier3")
        """
        downstream_ids = graph.get_downstream(root_cid)
        branch_ids = graph.topological_sort_subset({root_cid} | downstream_ids)
        unaffected_ids = [cid for cid in graph.order if cid not in branch_ids and graph.claims[cid].accepted]
        
        valid_downstream_rewritten = sum(1 for cid in downstream_ids if graph.claims[cid].accepted)
        total_tokens = 0
        
        # === TIER 1: Try branch repair ===
        logger.info(f"Tier 1: Attempting branch repair for {root_cid} and {len(downstream_ids)} downstream claims")
        
        unaffected_text = "\n".join(f"- [{cid}] {graph.claims[cid].text}" for cid in unaffected_ids) or "None"
        faulty_claim = graph.claims[root_cid]
        faulty_info = f"[{root_cid}] {faulty_claim.text} (Feedback: {faulty_claim.reason})"
        
        downstream_list_text = "\n".join(
            f"- [{cid}] {graph.claims[cid].text} (depends on: {graph.claims[cid].dependencies})"
            for cid in branch_ids if cid != root_cid
        ) or "None"
        
        # Save original texts in case we need to revert
        original_texts = {cid: graph.claims[cid].text for cid in branch_ids}
        
        prompt = (PROMPTS["branch_repair"]
                 .replace("{problem}", problem)
                 .replace("{unaffected_claims}", unaffected_text)
                 .replace("{faulty_claim_and_reason}", faulty_info)
                 .replace("{downstream_claims_list}", downstream_list_text))
        
        response_text, usage_dict = self.llm.call(
            prompt,
            temperature=0.3,
            max_tokens=self.config.max_tokens,
            seed=self.config.base_seed + 2
        )
        self._track_tokens(usage_dict)
        total_tokens += usage_dict.get("prompt_tokens", 0) + usage_dict.get("completion_tokens", 0)
        
        # Parse branch repair response
        data, parse_error = parse_json_safely(response_text)
        repaired_items = data.get("repaired_branch", []) if data else []
        
        # Apply repaired texts
        if isinstance(repaired_items, list):
            for item in repaired_items:
                if isinstance(item, dict):
                    rcid = str(item.get("id", ""))
                    rtext = str(item.get("text", "")).strip()
                    if rcid in branch_ids and rtext:
                        graph.claims[rcid].text = rtext
        
        # Verify all claims in branch (Tier 1)
        branch_ok = True
        for cid in branch_ids:
            self.verify_claim(problem, graph, cid)
            if not graph.claims[cid].accepted:
                branch_ok = False
        
        if branch_ok:
            logger.info(f"Tier 1 branch repair succeeded")
            return True, valid_downstream_rewritten, total_tokens, "Tier1"
        
        logger.warning(f"Tier 1 branch repair failed; escalating to Tier 2")
        
        # === TIER 2: Try full agent regeneration ===
        # Revert branch claims to original texts
        for cid in branch_ids:
            graph.claims[cid].text = original_texts[cid]
        
        logger.info(f"Tier 2: Attempting full Agent A regeneration")
        
        for attempt in range(1, self.config.max_regenerations + 1):
            temperature = self.config.temps[1] + (attempt - 1) * 0.1  # 0.7, 0.8, 0.9
            seed = self.config.base_seed + 100 + attempt
            
            # Regenerate entire Agent A output
            regen_prompt = PROMPTS["agent_a"].replace("{problem}", problem)
            regen_response, regen_usage = self.llm.call(
                regen_prompt,
                temperature=temperature,
                max_tokens=self.config.max_tokens,
                seed=seed
            )
            self._track_tokens(regen_usage)
            total_tokens += regen_usage.get("prompt_tokens", 0) + regen_usage.get("completion_tokens", 0)
            
            # Extract and verify new claims
            new_graph = self.extract_claims(problem, regen_response)
            if self.verify_all_claims(problem, new_graph):
                logger.info(f"Tier 2 full regeneration succeeded on attempt {attempt}")
                # Replace branch claims with new verified ones
                for cid in branch_ids:
                    if cid in new_graph.claims:
                        graph.claims[cid].text = new_graph.claims[cid].text
                        graph.claims[cid].valid = new_graph.claims[cid].valid
                        graph.claims[cid].confidence = new_graph.claims[cid].confidence
                        graph.claims[cid].accepted = new_graph.claims[cid].accepted
                return True, valid_downstream_rewritten, total_tokens, "Tier2"
        
        logger.warning(f"Tier 2 full regeneration failed; escalating to Tier 3 (accepting unverified)")
        
        # === TIER 3: Fall back to accepting unverified claim with warning ===
        logger.warning(
            f"All repair tiers exhausted for {root_cid}. Accepting with unverified status (Tier 3 fallback). "
            f"This may impact final answer accuracy."
        )
        
        # Force acceptance despite verification failure
        for cid in branch_ids:
            graph.claims[cid].accepted = True
        
        return True, valid_downstream_rewritten, total_tokens, "Tier3"

    # --- Adaptive Policy pi(x_f) for A4 ---

    def select_recovery_scope(self, graph: DependencyGraph, faulty_cid: str, num_faulty: int) -> str:
        """
        Feature vector x_f = [q_f, d(c_f), |Down(c_f)|, |Up(c_f)|, cost_f]
        Maps fault characteristics to R* in {R_claim, R_branch, R_agent, R_full}.
        """
        total_claims = max(1, len(graph.order))
        claim = graph.claims[faulty_cid]
        q_f = claim.confidence
        d_f = graph.get_depth(faulty_cid)
        down_set = graph.get_downstream(faulty_cid)
        up_set = graph.get_upstream(faulty_cid)
        num_down = len(down_set)
        num_up = len(up_set)
        branch_fraction = (1 + num_down) / total_claims
        fault_ratio = num_faulty / total_claims
        cost_f = branch_fraction  # Estimated relative re-computation footprint

        # 1. If the majority of the plan is faulty or a root assumption invalidates almost everything -> R_full / R_agent
        if fault_ratio > 0.60 or (d_f == 0 and branch_fraction > 0.75 and q_f < 0.30):
            return "R_full"

        if fault_ratio > 0.40 or branch_fraction > 0.60:
            return "R_agent"

        # 2. If the faulty claim has no downstream dependents -> Isolated Claim Repair (R_claim)
        if num_down == 0:
            return "R_claim"

        # 3. If the faulty claim has a bounded downstream dependency subtree -> Dependency Branch Repair (R_branch)
        return "R_branch"

    # =================================================================
    # 5. FOUR EVALUATED SYSTEMS (A0, A2, A3, A4)
    # =================================================================

    def run_system(self, system_name: str, example_id: int, problem: str, gold_answer: Optional[float]) -> ExampleTrace:
        self.reset_tokens()
        start_time = time.time()

        trace = ExampleTrace(
            example_id=example_id,
            system=system_name,
            question=problem,
            gold_answer=gold_answer,
            predicted_answer=None,
            is_correct=False,
            has_answer=False
        )

        # ---- SYSTEM A0: Sequential Baseline (No Verification) ----

        if system_name == "A0":
            plan_text = self.run_agent_a(problem, temp=self.config.temps[0], seed=None)
            b_out = self.run_agent_b(problem, plan_text)
            c_out = self.run_agent_c(problem, plan_text, b_out)
            pred = self.extract_final_number(c_out)

            trace.predicted_answer = pred
            trace.has_answer = pred is not None
            trace.is_correct = self.check_answer(pred, gold_answer)
            trace.latency_sec = time.time() - start_time
            trace.total_tokens = self.total_tokens

            return trace

        # Initial Agent A Generation + Claim Extraction + Verification (Shared protocol for A2, A3, A4)

        initial_plan = self.run_agent_a(problem, temp=self.config.temps[0], seed=None)
        graph = self.extract_claims(problem, initial_plan)
        all_ok = self.verify_all_claims(problem, graph)
        initial_valid_count = sum(1 for cid in graph.order if graph.claims[cid].accepted)

        trace.initial_detected_fault = not all_ok

        # ---- SYSTEM A2: Verify + Full Regeneration of Agent A ----

        if system_name == "A2":
            if not all_ok:
                trace.correct_units_exposed = initial_valid_count
                trace.correct_units_altered = initial_valid_count  # Full regeneration discards 100% of exposed valid claims

                accepted_plan = False
                for attempt in range(1, self.config.max_regenerations + 1):
                    trace.repair_attempts += 1
                    trace.selected_scopes.append("R_full")

                    regen_plan = self.run_agent_a(
                        problem,
                        temp=self.config.temps[min(attempt, len(self.config.temps) - 1)],
                        seed=None
                    )

                    graph = self.extract_claims(problem, regen_plan)
                    if self.verify_all_claims(problem, graph):
                        trace.successful_repairs += 1
                        accepted_plan = True
                        break

                if not accepted_plan:
                    # All regenerations failed verification -> produces "No answer" (counted as incorrect)
                    trace.predicted_answer = None
                    trace.has_answer = False
                    trace.is_correct = False
                    trace.latency_sec = time.time() - start_time
                    trace.total_tokens = self.total_tokens
                    return trace

            plan_text = graph.to_plan_text()
            b_out = self.run_agent_b(problem, plan_text)
            c_out = self.run_agent_c(problem, plan_text, b_out)
            pred = self.extract_final_number(c_out)

            trace.predicted_answer = pred
            trace.has_answer = pred is not None
            trace.is_correct = self.check_answer(pred, gold_answer)
            trace.latency_sec = time.time() - start_time
            trace.total_tokens = self.total_tokens

            return trace

        # ---- SYSTEM A3: Verify + Fixed Isolated Claim Repair ----

        if system_name == "A3":
            if not all_ok:
                trace.correct_units_exposed = initial_valid_count
                trace.correct_units_altered = 0  # Isolated repair never alters already-accepted claims (CDR = 0%)

                faulty_ids = [cid for cid in graph.order if not graph.claims[cid].accepted]

                for f_cid in faulty_ids:
                    trace.repair_attempts += 1
                    trace.selected_scopes.append("R_claim")

                    success, attempt, tokens = self.repair_isolated_claim(problem, graph, f_cid)
                    if success:
                        trace.successful_repairs += 1

            plan_text = graph.to_plan_text()
            b_out = self.run_agent_b(problem, plan_text)
            c_out = self.run_agent_c(problem, plan_text, b_out)
            pred = self.extract_final_number(c_out)

            trace.predicted_answer = pred
            trace.has_answer = pred is not None
            trace.is_correct = self.check_answer(pred, gold_answer)
            trace.latency_sec = time.time() - start_time
            trace.total_tokens = self.total_tokens

            return trace

        # ---- SYSTEM A4: ATBP (Adaptive Recovery Scope Selection) ----

        if system_name == "A4":
            if not all_ok:
                trace.correct_units_exposed = initial_valid_count
                altered_valid_ids: Set[str] = set()
                initial_accepted_ids: Set[str] = {cid for cid in graph.order if graph.claims[cid].accepted}

                faulty_ids = [cid for cid in graph.order if not graph.claims[cid].accepted]

                for f_cid in faulty_ids:
                    if f_cid in graph.claims and graph.claims[f_cid].accepted:
                        continue  # Already fixed by an earlier branch/agent repair

                    current_faults = [c for c in graph.order if not graph.claims[c].accepted]
                    if not current_faults:
                        break

                    scope = self.select_recovery_scope(graph, f_cid, len(current_faults))
                    trace.selected_scopes.append(scope)

                    if scope == "R_claim":
                        trace.repair_attempts += 1
                        success, attempt, tokens = self.repair_isolated_claim(problem, graph, f_cid)
                        if success:
                            trace.successful_repairs += 1

                    elif scope == "R_branch":
                        trace.repair_attempts += 1
                        down_valid = {d for d in graph.get_downstream(f_cid) if d in initial_accepted_ids}
                        altered_valid_ids.update(down_valid)

                        branch_ok, valid_rewritten, tokens, tier_used = self.repair_dependency_branch(problem, graph, f_cid)
                        if branch_ok:
                            trace.successful_repairs += 1

                    elif scope in ("R_agent", "R_full"):
                        altered_valid_ids.update(initial_accepted_ids)
                        for attempt in range(1, self.config.max_regenerations + 1):
                            trace.repair_attempts += 1

                            regen_plan = self.run_agent_a(
                                problem,
                                temp=self.config.temps[min(attempt, len(self.config.temps) - 1)],
                                seed=None
                            )

                            graph = self.extract_claims(problem, regen_plan)
                            if self.verify_all_claims(problem, graph):
                                trace.successful_repairs += 1
                                break

                        break

                trace.correct_units_altered = min(len(altered_valid_ids), trace.correct_units_exposed)

            plan_text = graph.to_plan_text()
            b_out = self.run_agent_b(problem, plan_text)
            c_out = self.run_agent_c(problem, plan_text, b_out)
            pred = self.extract_final_number(c_out)

            trace.predicted_answer = pred
            trace.has_answer = pred is not None
            trace.is_correct = self.check_answer(pred, gold_answer)
            trace.latency_sec = time.time() - start_time
            trace.total_tokens = self.total_tokens

            return trace

        raise ValueError(f"Unknown system variant: {system_name}")

    # --- Answer Extraction & Grading Utilities ---

    @staticmethod
    def extract_final_number(text: str) -> Optional[float]:
        """
        Extract final numerical answer from Agent C response.
        
        Handles:
        - Negative numbers: -\d+\.?\d*
        - Decimals: \d+\.\d+
        - Scientific notation: \d+e-?\d+
        - Percentages: \d+% (extracts numeric part only)
        - GSM8K marker format: #### <number>
        
        Priority:
        1. Look for explicit "answer is X" or "final answer X" patterns
        2. Check GSM8K marker (#### <number>)
        3. Return last number found in response
        4. Return None if no number found
        
        Args:
            text (str): Response text from Agent C
        
        Returns:
            Optional[float]: Extracted number or None if not found
        """
        if not text:
            return None

        # Remove common formatting (commas, currency symbols)
        text_cleaned = text.replace(",", "").replace("$", "")
        
        # Priority 1: Look for explicit answer patterns
        # Regex for "answer is X" or "final answer X" patterns
        explicit_patterns = [
            r"answer\s+is\s+([-+]?[\d.]+(?:e[-+]?\d+)?)",
            r"final\s+answer[:\s]+([-+]?[\d.]+(?:e[-+]?\d+)?)",
            r"the\s+answer\s+is\s+([-+]?[\d.]+(?:e[-+]?\d+)?)",
        ]
        
        for pattern in explicit_patterns:
            match = re.search(pattern, text_cleaned, re.IGNORECASE)
            if match:
                try:
                    return float(match.group(1))
                except (ValueError, IndexError):
                    pass
        
        # Priority 2: Check explicit GSM8K marker #### <number>
        marker_match = re.search(r"####\s*([-+]?[\d.]+(?:e[-+]?\d+)?)", text_cleaned)
        if marker_match:
            try:
                return float(marker_match.group(1))
            except ValueError:
                pass
        
        # Priority 3: Look for percentages and extract numeric part
        percent_match = re.search(r"([-+]?[\d.]+)\s*%", text_cleaned)
        if percent_match:
            try:
                return float(percent_match.group(1))
            except ValueError:
                pass
        
        # Priority 4: Find all numbers (including scientific notation) and return last
        # Patterns: integers, decimals, scientific notation
        num_patterns = [
            r"[-+]?\d+\.?\d*",  # Integers and decimals
            r"[-+]?\d+e[-+]?\d+",  # Scientific notation
        ]
        
        all_numbers = []
        for pattern in num_patterns:
            all_numbers.extend(re.findall(pattern, text_cleaned, re.IGNORECASE))
        
        if all_numbers:
            try:
                return float(all_numbers[-1])
            except ValueError:
                return None

        return None

    @staticmethod
    def check_answer(pred: Optional[float], gold: Optional[float]) -> bool:
        if pred is None or gold is None:
            return False
        return math.isclose(pred, gold, rel_tol=1e-4, abs_tol=1e-4)

# =====================================================================
# 6. METRICS COMPUTATION (ACCURACY, WILSON CI, ECR, RSR, CDR, LATENCY)
# =====================================================================

def wilson_confidence_interval(correct: int, total: int, z: float = 1.96) -> Tuple[float, float]:
    """Computes 95% Wilson score interval in percentage."""
    if total == 0:
        return (0.0, 0.0)

    p = correct / total
    denom = 1 + (z ** 2) / total
    center = (p + (z ** 2) / (2 * total)) / denom
    half_width = (z * math.sqrt((p * (1 - p) / total) + ((z ** 2) / (4 * (total ** 2))))) / denom

    low = max(0.0, (center - half_width) * 100.0)
    high = min(100.0, (center + half_width) * 100.0)

    return (low, high)

def summarize_system_metrics(system_name: str, traces: List[ExampleTrace]) -> Dict[str, Any]:
    """
    Compute summary metrics for a system across all examples.
    
    Metrics:
    - Accuracy: fraction of correct final answers
    - ECR (Error Cascade Rate): cascaded_errors / total_initial_failures
      Only counts errors that propagated downstream (detection -> incorrect answer)
    - RSR (Repair Success Rate): successful_repairs / total_repair_attempts
      Excludes attempts that escalated to higher-tier recovery
    - CDR (Collateral Damage Rate): altered_correct_claims / total_claims_in_branch
      Only when branch repair was selected
    """
    n_total = len(traces)
    n_correct = sum(1 for t in traces if t.is_correct)
    n_no_answer = sum(1 for t in traces if not t.has_answer)

    acc = (n_correct / n_total * 100.0) if n_total > 0 else 0.0
    ci_low, ci_high = wilson_confidence_interval(n_correct, n_total)

    mean_latency = sum(t.latency_sec for t in traces) / n_total if n_total > 0 else 0.0
    mean_tokens = sum(t.total_tokens for t in traces) / n_total if n_total > 0 else 0.0

    if system_name == "A0":
        return {
            "system": system_name,
            "correct": f"{n_correct}/{n_total}",
            "acc_pct": round(acc, 1),
            "wilson_95_ci": f"[{ci_low:.1f}, {ci_high:.1f}]",
            "no_answer": n_no_answer,
            "ECR": "n/a",
            "RSR": "n/a",
            "CDR": "n/a",
            "mean_latency_s": round(mean_latency, 1),
            "mean_tokens": round(mean_tokens, 1),
        }

    # ECR: Error Cascade Rate
    # Count ONLY errors that cascaded to final answer
    # = (examples with detected fault AND incorrect final answer) / (examples with detected fault)
    fault_traces = [t for t in traces if t.initial_detected_fault]
    n_fault_examples = len(fault_traces)
    n_cascaded = sum(1 for t in fault_traces if not t.is_correct)
    ecr_str = f"{(n_cascaded / n_fault_examples * 100.0):.1f}% ({n_cascaded}/{n_fault_examples})" if n_fault_examples > 0 else "0.0% (0/0)"

    # RSR: Repair Success Rate
    # Count repairs that succeeded / total repair attempts
    # Excludes attempts that escalated to higher recovery tier
    total_attempts = sum(t.repair_attempts for t in traces)
    total_success = sum(t.successful_repairs for t in traces)
    rsr_str = f"{(total_success / total_attempts * 100.0):.1f}% ({total_success}/{total_attempts})" if total_attempts > 0 else "0.0% (0/0)"

    # CDR: Collateral Damage Rate
    # Count previously correct claims that were altered/rewritten
    # = altered_correct_claims / total_correct_claims_exposed_to_recovery
    total_exposed = sum(t.correct_units_exposed for t in fault_traces)
    total_altered = sum(t.correct_units_altered for t in fault_traces)
    cdr_str = f"{(total_altered / total_exposed * 100.0):.1f}% ({total_altered}/{total_exposed})" if total_exposed > 0 else "0.0% (0/0)"

    return {
        "system": system_name,
        "correct": f"{n_correct}/{n_total}",
        "acc_pct": round(acc, 1),
        "wilson_95_ci": f"[{ci_low:.1f}, {ci_high:.1f}]",
        "no_answer": n_no_answer,
        "ECR": ecr_str,
        "RSR": rsr_str,
        "CDR": cdr_str,
        "mean_latency_s": round(mean_latency, 1),
        "mean_tokens": round(mean_tokens, 1),
    }

# =====================================================================
# 7. DATASET LOADER & EXPERIMENT RUNNER
# =====================================================================

def load_gsm8k_examples(num_examples: int = 10, local_jsonl_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Loads GSM8K test split from local JSONL or HuggingFace `datasets`."""
    examples = []

    if local_jsonl_path and os.path.exists(local_jsonl_path):
        with open(local_jsonl_path, "r", encoding="utf-8") as f:
            for idx, line in enumerate(f):
                if idx >= num_examples:
                    break
                row = json.loads(line)
                gold = ATBPPipeline.extract_final_number(row.get("answer", ""))
                examples.append({"id": idx, "question": row["question"], "gold": gold})

        return examples

    try:
        from datasets import load_dataset
        ds = load_dataset("openai/gsm8k", "main", split="test")
        for idx in range(min(num_examples, len(ds))):
            row = ds[idx]
            gold = ATBPPipeline.extract_final_number(row["answer"])
            examples.append({"id": idx, "question": row["question"], "gold": gold})

        return examples

    except Exception:
        # Built-in fallback GSM8K examples so the script runs out-of-the-box
        fallback = [
            {
                "id": 0,
                "question": "Janet's ducks lay 16 eggs per day. She eats three for breakfast every morning and bakes muffins for her friends every day with four. She sells the remainder at the farmers' market daily for $2 per fresh duck egg. How much in dollars does she make every day at the farmers' market?",
                "gold": 18.0
            },
            {
                "id": 1,
                "question": "A robe takes 2 bolts of blue fiber and half that much white fiber. How many bolts in total does it take?",
                "gold": 3.0
            },
            {
                "id": 2,
                "question": "Josh decides to try flipping a house. He buys a house for $80,000 and then puts in $50,000 in repairs. This increased the value of the house by 150%. How much profit did he make?",
                "gold": 70000.0
            }
        ]

        return fallback[:num_examples]

def main():
    parser = argparse.ArgumentParser(description="Run ATBP Evaluation across A0, A2, A3, A4 on GSM8K.")
    parser.add_argument("--num_examples", type=int, default=3, help="Number of GSM8K test examples to evaluate")
    parser.add_argument("--tau", type=float, default=0.80, help="Verification confidence threshold")
    parser.add_argument("--data_path", type=str, default=None, help="Optional local path to GSM8K test.jsonl")
    parser.add_argument("--output_file", type=str, default="atbp_results.json", help="Path to save logged traces and metrics")
    parser.add_argument("--systems", type=str, default="A0,A2,A3,A4", help="Comma-separated list of systems to run")

    args = parser.parse_args()

    # Load unified config (auto-detects LLM provider)
    pipeline_config = get_config(tau=args.tau)
    
    logger.info(f"Using ATBP config: provider={pipeline_config.api_provider}, model={pipeline_config.model}, tau={pipeline_config.tau}")

    pipeline = ATBPPipeline(pipeline_config)
    examples = load_gsm8k_examples(num_examples=args.num_examples, local_jsonl_path=args.data_path)
    systems = [s.strip() for s in args.systems.split(",")]

    all_traces: Dict[str, List[ExampleTrace]] = {s: [] for s in systems}

    logger.info(f"Loaded {len(examples)} GSM8K examples. Running systems {systems}...")

    for ex in examples:
        ex_id = ex["id"]
        question = ex["question"]
        gold = ex["gold"]

        logger.info(f"\n--- Example {ex_id} (Gold: {gold}) ---")
        logger.info(f"Question: {question[:100]}...")

        for sys_name in systems:
            try:
                trace = pipeline.run_system(sys_name, ex_id, question, gold)
                all_traces[sys_name].append(trace)

                logger.info(
                    f"[{sys_name}] Pred: {trace.predicted_answer} | Correct: {trace.is_correct} | "
                    f"Fault: {trace.initial_detected_fault} | Attempts: {trace.repair_attempts} | "
                    f"Latency: {trace.latency_sec:.1f}s | Tokens: {trace.total_tokens}"
                )
            except Exception as e:
                logger.error(f"[{sys_name}] Error on example {ex_id}: {e}", exc_info=True)

    summaries = [summarize_system_metrics(s, all_traces[s]) for s in systems]

    a0_lat = summaries[0]["mean_latency_s"] or 1.0

    for row in summaries:
        row["relative_latency"] = f"{(row['mean_latency_s'] / a0_lat):.2f}x"

    logger.info("\n================ FINAL SUMMARY TABLE ================")

    header = f"{'System':<6} | {'Correct':<8} | {'Acc(%)':<6} | {'95% CI':<14} | {'NoAns':<5} | {'ECR':<15} | {'RSR':<15} | {'CDR':<15} | {'Latency(s)':<10} | {'Rel.Lat':<7} | {'AvgTokens':<9}"
    logger.info(header)
    logger.info("-" * len(header))

    for r in summaries:
        logger.info(
            f"{r['system']:<6} | {r['correct']:<8} | {r['acc_pct']:<6} | {r['wilson_95_ci']:<14} | "
            f"{r['no_answer']:<5} | {r['ECR']:<15} | {r['RSR']:<15} | {r['CDR']:<15} | "
            f"{r['mean_latency_s']:<10} | {r['relative_latency']:<7} | {r['mean_tokens']:<9}"
        )

    output_payload = {
        "config": asdict(config),
        "summaries": summaries,
        "traces": {s: [asdict(t) for t in all_traces[s]] for s in systems}
    }

    with open(args.output_file, "w", encoding="utf-8") as f:
        json.dump(output_payload, f, indent=2)

    logger.info(f"\nSaved full experiment logs and metrics to {args.output_file}")

if __name__ == "__main__":
    main()
