"""
Unified evaluation of:

A2 = Verify + Full Regeneration
A3 = Verify + Fixed Targeted Repair

The implementation is deliberately model-agnostic. It uses the
existing pipeline/model interface where available and keeps recovery
logic separate from the LLM implementation.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------

DEFAULT_TAU = 0.80
DEFAULT_MAX_REGENERATIONS = 3


# ----------------------------------------------------------------------
# Data structures
# ----------------------------------------------------------------------

@dataclass
class Claim:
    claim_id: str
    text: str
    confidence: float = 1.0
    is_valid: bool = True


@dataclass
class RecoveryResult:
    strategy: str
    success: bool

    original_plan: str
    repaired_plan: str

    detected_faults: int
    repaired_faults: int

    regeneration_attempts: int

    input_tokens: int = 0
    output_tokens: int = 0
    latency_seconds: float = 0.0

    claims_before: int = 0
    claims_after: int = 0

    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


# ----------------------------------------------------------------------
# Claim extraction
# ----------------------------------------------------------------------

def extract_claims(plan: str) -> List[Claim]:
    """
    Convert an Agent-A plan into atomic claims.

    This function first attempts to interpret each non-empty line as
    an atomic claim. If your project already has a dedicated LLM
    claim extractor, replace this function's body with that extractor.

    Keeping the interface as List[Claim] means A2/A3 do not need to
    change.
    """

    lines = [
        line.strip()
        for line in plan.splitlines()
        if line.strip()
    ]

    claims: List[Claim] = []

    for index, line in enumerate(lines):
        # Remove common list prefixes.
        text = line

        for prefix in (
            "- ",
            "* ",
            "• ",
        ):
            if text.startswith(prefix):
                text = text[len(prefix):].strip()

        if text:
            claims.append(
                Claim(
                    claim_id=f"c{index + 1}",
                    text=text,
                )
            )

    return claims


# ----------------------------------------------------------------------
# Claim verification
# ----------------------------------------------------------------------

def verify_claim(
    claim: Claim,
    context: str,
    tau: float,
) -> Claim:
    """
    Verify one claim.

    IMPORTANT:
    Replace the body with the project's existing claim verifier when
    available.

    The expected output is simply:

        claim.is_valid
        claim.confidence
    """

    # --------------------------------------------------------------
    # Placeholder deterministic verifier.
    #
    # This is intentionally conservative. It should be replaced by
    # src/verification/claim_verifier.py once that component exists
    # in the working repository.
    # --------------------------------------------------------------

    claim.confidence = 1.0
    claim.is_valid = True

    return claim


def verify_all_claims(
    claims: Sequence[Claim],
    context: str,
    tau: float,
) -> List[Claim]:

    verified = []

    for claim in claims:
        verified.append(
            verify_claim(
                claim,
                context=context,
                tau=tau,
            )
        )

    return verified


def get_failed_claims(
    claims: Sequence[Claim],
    tau: float,
) -> List[Claim]:

    return [
        claim
        for claim in claims
        if (
            not claim.is_valid
            or claim.confidence < tau
        )
    ]


# ----------------------------------------------------------------------
# Plan reconstruction
# ----------------------------------------------------------------------

def reconstruct_plan(
    claims: Sequence[Claim],
) -> str:
    """
    Deterministically reconstruct Agent-A's plan from atomic claims.
    """

    return "\n".join(
        claim.text
        for claim in claims
    )


# ----------------------------------------------------------------------
# LLM adapter
# ----------------------------------------------------------------------

class LLMAdapter:
    """
    Thin adapter around the project's LLM.

    Replace call() with the existing call_llm() function from
    src.pipeline once your local project exposes that function.

    Keeping this adapter here prevents recovery logic from becoming
    coupled to Ollama/OpenAI/Groq/litellm.
    """

    def __init__(self, model=None):
        self.model = model

    def call(
        self,
        prompt: str,
    ) -> str:

        # ----------------------------------------------------------
        # IMPORTANT:
        # Replace this section with:
        #
        # from src.pipeline import call_llm
        # return call_llm(prompt)
        #
        # if your pipeline exposes call_llm().
        # ----------------------------------------------------------

        raise NotImplementedError(
            "Connect LLMAdapter.call() to "
            "your existing call_llm() implementation."
        )


# ----------------------------------------------------------------------
# Agent-A regeneration
# ----------------------------------------------------------------------

def regenerate_full_plan(
    llm: LLMAdapter,
    original_plan: str,
    context: str,
) -> str:

    prompt = f"""
You are Agent A in a multi-agent reasoning system.

The previous plan was rejected because one or more intermediate
claims failed verification.

Generate a completely new plan.

Do NOT preserve the previous plan merely because it already exists.
Re-evaluate the problem from the beginning.

Context:
{context}

Previous plan:
{original_plan}

Return only the new reasoning plan.
""".strip()

    return llm.call(prompt)


def repair_single_claim(
    llm: LLMAdapter,
    claim: Claim,
    context: str,
    failure_reason: str = "",
) -> str:

    prompt = f"""
You are repairing ONE atomic claim inside a multi-agent reasoning
pipeline.

Original claim:
{claim.text}

Verification failure:
{failure_reason}

Context:
{context}

Produce a corrected version of ONLY this claim.

Do not rewrite unrelated claims.
Do not add explanations.
Return only the corrected claim.
""".strip()

    return llm.call(prompt).strip()


# ----------------------------------------------------------------------
# A2
# ----------------------------------------------------------------------

def evaluate_a2(
    original_plan: str,
    context: str,
    llm: LLMAdapter,
    tau: float = DEFAULT_TAU,
    max_regenerations: int = DEFAULT_MAX_REGENERATIONS,
) -> RecoveryResult:

    start = time.perf_counter()

    claims = extract_claims(
        original_plan
    )

    verified = verify_all_claims(
        claims,
        context=context,
        tau=tau,
    )

    failed = get_failed_claims(
        verified,
        tau=tau,
    )

    # --------------------------------------------------------------
    # No fault: keep original generation.
    # --------------------------------------------------------------

    if not failed:
        return RecoveryResult(
            strategy="A2",
            success=True,
            original_plan=original_plan,
            repaired_plan=original_plan,
            detected_faults=0,
            repaired_faults=0,
            regeneration_attempts=0,
            latency_seconds=(
                time.perf_counter() - start
            ),
            claims_before=len(claims),
            claims_after=len(claims),
        )

    # --------------------------------------------------------------
    # Fault detected:
    #
    # A2 discards the ENTIRE plan.
    # --------------------------------------------------------------

    current_plan = original_plan
    attempts = 0

    while attempts < max_regenerations:

        attempts += 1

        current_plan = regenerate_full_plan(
            llm=llm,
            original_plan=current_plan,
            context=context,
        )

        regenerated_claims = extract_claims(
            current_plan
        )

        regenerated_claims = verify_all_claims(
            regenerated_claims,
            context=context,
            tau=tau,
        )

        remaining_faults = get_failed_claims(
            regenerated_claims,
            tau=tau,
        )

        if not remaining_faults:

            return RecoveryResult(
                strategy="A2",
                success=True,
                original_plan=original_plan,
                repaired_plan=current_plan,
                detected_faults=len(failed),
                repaired_faults=len(failed),
                regeneration_attempts=attempts,
                latency_seconds=(
                    time.perf_counter() - start
                ),
                claims_before=len(claims),
                claims_after=len(
                    regenerated_claims
                ),
            )

    # --------------------------------------------------------------
    # Full regeneration budget exhausted.
    # --------------------------------------------------------------

    return RecoveryResult(
        strategy="A2",
        success=False,
        original_plan=original_plan,
        repaired_plan=current_plan,
        detected_faults=len(failed),
        repaired_faults=(
            len(failed)
            - len(remaining_faults)
        ),
        regeneration_attempts=attempts,
        latency_seconds=(
            time.perf_counter() - start
        ),
        claims_before=len(claims),
        claims_after=len(
            extract_claims(current_plan)
        ),
    )


# ----------------------------------------------------------------------
# A3
# ----------------------------------------------------------------------

def evaluate_a3(
    original_plan: str,
    context: str,
    llm: LLMAdapter,
    tau: float = DEFAULT_TAU,
) -> RecoveryResult:

    start = time.perf_counter()

    claims = extract_claims(
        original_plan
    )

    verified = verify_all_claims(
        claims,
        context=context,
        tau=tau,
    )

    failed = get_failed_claims(
        verified,
        tau=tau,
    )

    # --------------------------------------------------------------
    # No fault.
    # --------------------------------------------------------------

    if not failed:
        return RecoveryResult(
            strategy="A3",
            success=True,
            original_plan=original_plan,
            repaired_plan=original_plan,
            detected_faults=0,
            repaired_faults=0,
            regeneration_attempts=0,
            latency_seconds=(
                time.perf_counter() - start
            ),
            claims_before=len(claims),
            claims_after=len(claims),
        )

    # --------------------------------------------------------------
    # TARGETED REPAIR
    #
    # Only failed claims are regenerated.
    # --------------------------------------------------------------

    repaired_claims: List[Claim] = []

    failed_ids = {
        claim.claim_id
        for claim in failed
    }

    for claim in verified:

        if claim.claim_id not in failed_ids:
            # Critical property of A3:
            # valid claims remain untouched.
            repaired_claims.append(
                claim
            )
            continue

        repaired_text = repair_single_claim(
            llm=llm,
            claim=claim,
            context=context,
        )

        repaired_claims.append(
            Claim(
                claim_id=claim.claim_id,
                text=repaired_text,
            )
        )

    repaired_plan = reconstruct_plan(
        repaired_claims
    )

    # --------------------------------------------------------------
    # Verify repaired claims.
    # --------------------------------------------------------------

    repaired_verified = verify_all_claims(
        repaired_claims,
        context=context,
        tau=tau,
    )

    remaining_faults = get_failed_claims(
        repaired_verified,
        tau=tau,
    )

    repaired_fault_count = (
        len(failed)
        - len(remaining_faults)
    )

    return RecoveryResult(
        strategy="A3",
        success=len(remaining_faults) == 0,
        original_plan=original_plan,
        repaired_plan=repaired_plan,
        detected_faults=len(failed),
        repaired_faults=repaired_fault_count,
        regeneration_attempts=len(failed),
        latency_seconds=(
            time.perf_counter() - start
        ),
        claims_before=len(claims),
        claims_after=len(
            repaired_claims
        ),
        metadata={
            "failed_claim_ids": sorted(
                failed_ids
            ),
            "remaining_fault_ids": [
                claim.claim_id
                for claim in remaining_faults
            ],
        },
    )


# ----------------------------------------------------------------------
# Evaluation
# ----------------------------------------------------------------------

def run_evaluation(
    examples: Sequence[Dict[str, Any]],
    llm: LLMAdapter,
    tau: float,
    max_regenerations: int,
    output_path: Path,
) -> None:

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with output_path.open(
        "w",
        encoding="utf-8",
    ) as output:

        for index, example in enumerate(
            examples,
            start=1,
        ):

            question = example.get(
                "question",
                "",
            )

            context = example.get(
                "context",
                "",
            )

            original_plan = example.get(
                "plan",
                "",
            )

            # -------------------------
            # A2
            # -------------------------

            a2 = evaluate_a2(
                original_plan=original_plan,
                context=context,
                llm=llm,
                tau=tau,
                max_regenerations=max_regenerations,
            )

            # -------------------------
            # A3
            # -------------------------

            a3 = evaluate_a3(
                original_plan=original_plan,
                context=context,
                llm=llm,
                tau=tau,
            )

            record = {
                "example_id": example.get(
                    "id",
                    index,
                ),
                "question": question,
                "a2": asdict(a2),
                "a3": asdict(a3),
            }

            output.write(
                json.dumps(
                    record,
                    ensure_ascii=False,
                )
                + "\n"
            )

            print(
                f"[{index}/{len(examples)}] "
                f"A2={a2.success} "
                f"A3={a3.success}"
            )


# ----------------------------------------------------------------------
# Dataset loading
# ----------------------------------------------------------------------

def load_jsonl(
    path: Path,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:

    examples = []

    with path.open(
        "r",
        encoding="utf-8",
    ) as file:

        for line in file:

            line = line.strip()

            if not line:
                continue

            examples.append(
                json.loads(line)
            )

            if (
                limit is not None
                and len(examples) >= limit
            ):
                break

    return examples


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Evaluate ATBP A2 and A3 recovery strategies."
        )
    )

    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Input JSONL file.",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "results/recovery_results.jsonl"
        ),
        help="Output JSONL file.",
    )

    parser.add_argument(
        "--tau",
        type=float,
        default=DEFAULT_TAU,
        help="Verification confidence threshold.",
    )

    parser.add_argument(
        "--max-regens",
        type=int,
        default=DEFAULT_MAX_REGENERATIONS,
        help="Maximum full regenerations for A2.",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Number of examples to evaluate.",
    )

    args = parser.parse_args()

    examples = load_jsonl(
        args.input,
        limit=args.limit,
    )

    llm = LLMAdapter()

    run_evaluation(
        examples=examples,
        llm=llm,
        tau=args.tau,
        max_regenerations=args.max_regens,
        output_path=args.output,
    )


if __name__ == "__main__":
    main()