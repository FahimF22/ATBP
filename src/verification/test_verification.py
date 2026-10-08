from src.verification.claim_extractor import extract_claims


problem = """
A store has 12 apples.
It sells 5 apples.
How many apples remain?
"""

reasoning = """
The store starts with 12 apples.
It sells 5 apples.
Therefore, 7 apples remain.
"""

claims = extract_claims(
    problem,
    reasoning
)

for claim in claims:
    print(claim)