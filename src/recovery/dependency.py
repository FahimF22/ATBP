"""
Dependency tracking for atomic claims.

The graph represents premise/dependency relationships between claims.

If:

    c2 depends on c1

then the graph contains:

    c1 -> c2

This allows ATBP to determine:
    - direct dependents
    - transitive dependents
    - prerequisites
    - dependency depth
    - recovery scope
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Set
from src.verification.claim_extractor import extract_claims



@dataclass
class ClaimNode:
    """
    Represents one atomic claim extracted from an agent's reasoning.
    """

    claim_id: str
    text: str

    agent_id: Optional[str] = None
    confidence: Optional[float] = None
    is_valid: Optional[bool] = None

    # Claims that this claim directly depends upon.
    prerequisites: Set[str] = field(default_factory=set)

    # Claims that directly depend upon this claim.
    dependents: Set[str] = field(default_factory=set)


class DependencyGraph:
    """
    Directed acyclic graph over atomic claims.

    Edge:

        A -> B

    means:

        B depends on A.

    The graph is intentionally independent of the LLM implementation.
    """

    def __init__(self) -> None:
        self.nodes: Dict[str, ClaimNode] = {}

    # ------------------------------------------------------------------
    # Node management
    # ------------------------------------------------------------------

    def add_claim(
        self,
        claim_id: str,
        text: str,
        agent_id: Optional[str] = None,
        confidence: Optional[float] = None,
        is_valid: Optional[bool] = None,
    ) -> ClaimNode:
        """
        Add a claim to the graph.

        Raises:
            ValueError: if claim_id already exists.
        """

        if claim_id in self.nodes:
            raise ValueError(
                f"Claim '{claim_id}' already exists."
            )

        node = ClaimNode(
            claim_id=claim_id,
            text=text,
            agent_id=agent_id,
            confidence=confidence,
            is_valid=is_valid,
        )

        self.nodes[claim_id] = node
        return node

    def get_claim(self, claim_id: str) -> ClaimNode:
        """Return a claim by ID."""

        if claim_id not in self.nodes:
            raise KeyError(
                f"Unknown claim ID: {claim_id}"
            )

        return self.nodes[claim_id]

    # ------------------------------------------------------------------
    # Edge management
    # ------------------------------------------------------------------

    def add_dependency(
        self,
        prerequisite_id: str,
        dependent_id: str,
    ) -> None:
        """
        Add:

            prerequisite_id -> dependent_id

        meaning dependent_id relies on prerequisite_id.
        """

        if prerequisite_id not in self.nodes:
            raise KeyError(
                f"Unknown prerequisite claim: {prerequisite_id}"
            )

        if dependent_id not in self.nodes:
            raise KeyError(
                f"Unknown dependent claim: {dependent_id}"
            )

        if prerequisite_id == dependent_id:
            raise ValueError(
                "A claim cannot depend on itself."
            )

        # Temporarily add the edge.
        self.nodes[prerequisite_id].dependents.add(
            dependent_id
        )

        self.nodes[dependent_id].prerequisites.add(
            prerequisite_id
        )

        # Ensure the graph remains acyclic.
        if self.has_cycle():
            self.nodes[prerequisite_id].dependents.remove(
                dependent_id
            )

            self.nodes[dependent_id].prerequisites.remove(
                prerequisite_id
            )

            raise ValueError(
                f"Adding dependency "
                f"{prerequisite_id} -> {dependent_id} "
                f"would create a cycle."
            )

    # ------------------------------------------------------------------
    # Traversal
    # ------------------------------------------------------------------

    def direct_dependents(
        self,
        claim_id: str,
    ) -> Set[str]:
        """Return claims directly depending on claim_id."""

        return set(
            self.get_claim(claim_id).dependents
        )

    def direct_prerequisites(
        self,
        claim_id: str,
    ) -> Set[str]:
        """Return claims directly required by claim_id."""

        return set(
            self.get_claim(claim_id).prerequisites
        )

    def downstream(
        self,
        claim_id: str,
    ) -> Set[str]:
        """
        Return all transitive downstream dependents.
        """

        self.get_claim(claim_id)

        visited: Set[str] = set()
        stack = list(
            self.nodes[claim_id].dependents
        )

        while stack:
            current = stack.pop()

            if current in visited:
                continue

            visited.add(current)

            stack.extend(
                self.nodes[current].dependents
            )

        return visited

    def upstream(
        self,
        claim_id: str,
    ) -> Set[str]:
        """
        Return all transitive prerequisites.
        """

        self.get_claim(claim_id)

        visited: Set[str] = set()
        stack = list(
            self.nodes[claim_id].prerequisites
        )

        while stack:
            current = stack.pop()

            if current in visited:
                continue

            visited.add(current)

            stack.extend(
                self.nodes[current].prerequisites
            )

        return visited

    # ------------------------------------------------------------------
    # Dependency depth
    # ------------------------------------------------------------------

    def dependency_depth(
        self,
        claim_id: str,
    ) -> int:
        """
        Return the longest prerequisite chain leading to claim_id.

        Example:

            c1 -> c2 -> c3

        gives:

            depth(c1) = 0
            depth(c2) = 1
            depth(c3) = 2
        """

        self.get_claim(claim_id)

        memo: Dict[str, int] = {}

        def depth(node_id: str) -> int:
            if node_id in memo:
                return memo[node_id]

            prerequisites = self.nodes[
                node_id
            ].prerequisites

            if not prerequisites:
                memo[node_id] = 0
                return 0

            value = 1 + max(
                depth(parent)
                for parent in prerequisites
            )

            memo[node_id] = value
            return value

        return depth(claim_id)

    # ------------------------------------------------------------------
    # Graph properties
    # ------------------------------------------------------------------

    def has_cycle(self) -> bool:
        """
        Detect whether the graph contains a cycle.
        """

        visited: Set[str] = set()
        active: Set[str] = set()

        def visit(node_id: str) -> bool:
            if node_id in active:
                return True

            if node_id in visited:
                return False

            visited.add(node_id)
            active.add(node_id)

            for dependent in self.nodes[
                node_id
            ].dependents:

                if visit(dependent):
                    return True

            active.remove(node_id)
            return False

        return any(
            visit(node_id)
            for node_id in self.nodes
        )

    def roots(self) -> List[str]:
        """
        Return claims that have no prerequisites.
        """

        return [
            node_id
            for node_id, node in self.nodes.items()
            if not node.prerequisites
        ]

    def leaves(self) -> List[str]:
        """
        Return claims that have no downstream dependents.
        """

        return [
            node_id
            for node_id, node in self.nodes.items()
            if not node.dependents
        ]

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict:
        """
        Convert the graph into a JSON-serializable dictionary.
        """

        return {
            "nodes": {
                claim_id: {
                    "claim_id": node.claim_id,
                    "text": node.text,
                    "agent_id": node.agent_id,
                    "confidence": node.confidence,
                    "is_valid": node.is_valid,
                    "prerequisites": sorted(
                        node.prerequisites
                    ),
                    "dependents": sorted(
                        node.dependents
                    ),
                    "depth": self.dependency_depth(
                        claim_id
                    ),
                }
                for claim_id, node in self.nodes.items()
            }
        }


def build_dependency_graph(
    claims: Iterable[dict],
) -> DependencyGraph:
    """
    Build a dependency graph from extracted atomic claims.

    Expected claim format:

        {
            "id": "c1",
            "text": "x = 5",
            "agent_id": "agent_a",
            "depends_on": []
        }

    or:

        {
            "claim_id": "c2",
            "text": "therefore x + 1 = 6",
            "depends_on": ["c1"]
        }

    The function accepts both 'id' and 'claim_id'.
    """

    graph = DependencyGraph()

    claims = list(claims)

    # First create every node.
    for index, claim in enumerate(claims):
        claim_id = (
            claim.get("claim_id")
            or claim.get("id")
            or f"c{index + 1}"
        )

        graph.add_claim(
            claim_id=claim_id,
            text=str(
                claim.get("text", "")
            ),
            agent_id=claim.get("agent_id"),
            confidence=claim.get(
                "confidence"
            ),
            is_valid=claim.get(
                "is_valid"
            ),
        )

    # Then create dependency edges.
    for index, claim in enumerate(claims):
        claim_id = (
            claim.get("claim_id")
            or claim.get("id")
            or f"c{index + 1}"
        )

        dependencies = (
            claim.get("depends_on")
            or claim.get("prerequisites")
            or []
        )

        for prerequisite_id in dependencies:
            graph.add_dependency(
                prerequisite_id=str(
                    prerequisite_id
                ),
                dependent_id=claim_id,
            )

    return graph