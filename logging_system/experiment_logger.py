import json
import os
from datetime import datetime


def save_experiment(record, filename="results/baseline_results.jsonl"):

    os.makedirs("results", exist_ok=True)

    record["timestamp"] = datetime.now().isoformat()

    with open(filename, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")