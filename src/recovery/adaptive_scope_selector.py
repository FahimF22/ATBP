"""
Adaptive scope selection for A4 recovery strategy.

Determines which recovery scope to apply based on:
- Verification results (confidence, failed claim count)
- Dependency graph (transitive dependencies)
- Problem characteristics (complexity, error depth)

Scopes:
- "isolated_claim": Repair single low-confidence claim
- "agent_level": Regenerate entire Agent A
- "dependency_branch": Repair all dependents of failed claim
- "full_regeneration": Discard entire pipeline and restart
"""

from typing import Dict, List, Optional, Any
from src.recovery.dependency import DependencyGraph


class AdaptiveScopeSelector:
    """
    Selects recovery scope based on verification results and dependency graph.
    """

    def __init__(self, tau=0.80):
        """
        Initialize selector.

        Args:
            tau: Verification threshold for claim acceptance
        """
        self.tau = tau

    def select_scope(
        self,
        claims: List[Dict[str, Any]],
        verification: List[Dict[str, Any]],
        dependency_graph: Optional[DependencyGraph] = None,
    ) -> Dict[str, Any]:
        """
        Select recovery scope based on verification results.

        Args:
            claims: List of extracted claims with claim_id, text
            verification: List of verification results with is_valid, confidence, claim_id
            dependency_graph: Optional DependencyGraph for scope analysis

        Returns:
            {
                "scope": "isolated_claim" | "agent_level" | "dependency_branch" | "full_regeneration",
                "target_claim_ids": [list of claim IDs to repair],
                "confidence_scores": [mean confidence of failed claims],
                "failed_count": number of failed claims,
                "rationale": human-readable explanation,
            }
        """

        # Identify failed claims
        failed = [v for v in verification if not v.get("is_valid", False)]
        failed_count = len(failed)
        total_count = len(verification)

        if failed_count == 0:
            return {
                "scope": "no_recovery",
                "target_claim_ids": [],
                "confidence_scores": [],
                "failed_count": 0,
                "rationale": "All claims verified successfully.",
            }

        # Compute mean confidence of failed claims
        confidences = [v.get("confidence", 0.0) for v in failed]
        mean_confidence = (
            sum(confidences) / len(confidences) if confidences else 0.0
        )

        # Compute failure rate
        failure_rate = failed_count / total_count if total_count > 0 else 1.0

        failed_ids = [v.get("claim_id") for v in failed]

        # Decision logic based on failure characteristics
        if failure_rate >= 0.5:
            # More than half the claims failed: full regeneration likely needed
            return {
                "scope": "full_regeneration",
                "target_claim_ids": failed_ids,
                "confidence_scores": confidences,
                "failed_count": failed_count,
                "rationale": f"Failure rate {failure_rate:.1%} exceeds 50%; full regeneration recommended.",
            }

        elif failed_count == 1:
            # Single claim failed: attempt isolated repair
            claim_id = failed_ids[0]

            if dependency_graph and claim_id in dependency_graph.nodes:
                downstream = dependency_graph.downstream(claim_id)
                if downstream:
                    # Has dependents: repair entire branch
                    return {
                        "scope": "dependency_branch",
                        "target_claim_ids": [claim_id] + list(downstream),
                        "confidence_scores": confidences,
                        "failed_count": failed_count,
                        "rationale": f"Single claim failed with {len(downstream)} downstream dependents; repairing branch.",
                    }

            # No dependents: isolated repair
            return {
                "scope": "isolated_claim",
                "target_claim_ids": failed_ids,
                "confidence_scores": confidences,
                "failed_count": failed_count,
                "rationale": "Single claim failed with no downstream dependents; isolated repair.",
            }

        else:
            # Multiple scattered failures: check if they're clustered
            if dependency_graph:
                # Find if failed claims share dependencies
                shared_dependencies = self._find_shared_dependencies(
                    failed_ids, dependency_graph
                )

                if shared_dependencies:
                    # Failures trace back to common root: repair that root's branch
                    repair_ids = [
                        failed_ids[0]
                    ] + self._get_affected_claims(
                        failed_ids[0], dependency_graph
                    )

                    return {
                        "scope": "dependency_branch",
                        "target_claim_ids": repair_ids,
                        "confidence_scores": confidences,
                        "failed_count": failed_count,
                        "rationale": f"Multiple failures share dependencies; repairing {len(repair_ids)} affected claims.",
                    }

            # Multiple scattered failures with no shared dependencies: agent-level repair
            return {
                "scope": "agent_level",
                "target_claim_ids": failed_ids,
                "confidence_scores": confidences,
                "failed_count": failed_count,
                "rationale": f"{failed_count} scattered failures detected; regenerating Agent A.",
            }

    def _find_shared_dependencies(
        self, claim_ids: List[str], dependency_graph: DependencyGraph
    ) -> List[str]:
        """
        Find claims that multiple failed claims depend on.
        """
        if not claim_ids or not dependency_graph:
            return []

        # Get prerequisites for each failed claim
        prerequisite_sets = []
        for claim_id in claim_ids:
            if claim_id in dependency_graph.nodes:
                prerequisites = dependency_graph.direct_prerequisites(claim_id)
                prerequisite_sets.append(prerequisites)

        if not prerequisite_sets:
            return []

        # Find intersection (shared dependencies)
        shared = set(prerequisite_sets[0])
        for prereq_set in prerequisite_sets[1:]:
            shared = shared.intersection(prereq_set)

        return list(shared)

    def _get_affected_claims(
        self, claim_id: str, dependency_graph: DependencyGraph
    ) -> List[str]:
        """
        Get all downstream claims affected by a given claim.
        """
        if claim_id not in dependency_graph.nodes:
            return []

        return list(dependency_graph.downstream(claim_id))


def select_recovery_scope(
    claims: List[Dict[str, Any]],
    verification: List[Dict[str, Any]],
    dependency_graph: Optional[DependencyGraph] = None,
    tau: float = 0.80,
) -> Dict[str, Any]:
    """
    Convenience function: select recovery scope for given claims and verification.
    """
    selector = AdaptiveScopeSelector(tau=tau)
    return selector.select_scope(claims, verification, dependency_graph)
