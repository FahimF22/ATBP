from src.recovery.dependency import build_dependency_graph


claims = [
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
        "text": "The store has 7 apples left.",
        "depends_on": ["c1", "c2"]
    }
]

graph = build_dependency_graph(claims)

print("c3 prerequisites:")
print(graph.direct_prerequisites("c3"))

print("c1 downstream:")
print(graph.downstream("c1"))

print("c3 depth:")
print(graph.dependency_depth("c3"))