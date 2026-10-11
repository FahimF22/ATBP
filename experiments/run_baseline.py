import sys
import time
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from datasets import load_dataset

from agents.agent_a import agent_a
from agents.agent_b import agent_b
from agents.agent_c import agent_c

from evaluation.gsm8k_evaluator import evaluate_answer

from logging_system.experiment_logger import save_experiment


def run_baseline(num_examples=5):

    dataset = load_dataset(
        "openai/gsm8k",
        "main",
        split="test"
    )

    correct = 0

    for i in range(num_examples):

        item = dataset[i]

        problem = item["question"]
        ground_truth = item["answer"]

        print("\n" + "=" * 70)
        print(f"Problem {i + 1}")
        print("=" * 70)

        start_time = time.time()

        # Agent A
        a_output = agent_a(problem)

        print("\n--- Agent A ---")
        print(a_output)

        # Agent B
        b_output = agent_b(
            problem,
            a_output
        )

        print("\n--- Agent B ---")
        print(b_output)

        # Agent C
        c_output = agent_c(
            problem,
            a_output,
            b_output
        )

        print("\n--- Agent C ---")
        print(c_output)

        latency = time.time() - start_time

        is_correct, prediction, answer = evaluate_answer(
            c_output,
            ground_truth
        )

        if is_correct:
            correct += 1

        record = {
            "problem_id": i,
            "problem": problem,

            "agent_a": a_output,
            "agent_b": b_output,
            "agent_c": c_output,

            "prediction": prediction,
            "ground_truth": answer,

            "correct": is_correct,

            "latency_seconds": latency
        }

        save_experiment(record)

        print("\nPrediction:", prediction)
        print("Ground truth:", answer)
        print("Correct:", is_correct)
        print("Latency:", round(latency, 2), "seconds")

    accuracy = correct / num_examples

    print("\n" + "=" * 70)
    print("BASELINE RESULTS")
    print("=" * 70)

    print(f"Examples: {num_examples}")
    print(f"Correct: {correct}")
    print(f"Accuracy: {accuracy:.4f}")


if __name__ == "__main__":
    run_baseline(num_examples=100)