
import os
import time
import requests

from logging_system.experiment_logger import save_experiment

from openai import OpenAI
from config.config import MODEL_NAME, MAX_TOKENS, TEMPERATURE

client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama"
)


def call_llm(system_prompt: str, user_content: str) -> tuple[str, int, int]:
    response = client.chat.completions.create(
        model=MODEL_NAME,
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
        messages=[
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": user_content
            }
        ]
    )

    text = response.choices[0].message.content or ""

    usage = response.usage
    prompt_tokens = usage.prompt_tokens if usage else 0
    completion_tokens = usage.completion_tokens if usage else 0

    return text.strip(), prompt_tokens, completion_tokens


def run_baseline_a0(task: dict):
    start_time = time.perf_counter()

    question = task["question"]
    context = task.get("context", "")

    record = {
        "task_id": task["id"],
        "method": "A0_Sequential",
        "model": MODEL_NAME,
        "steps": [],
        "total_prompt_tokens": 0,
        "total_completion_tokens": 0,
        "final_answer": None,
        "ground_truth": str(task["ground_truth"]),
        "is_correct": False,
        "total_latency": 0.0
    }

    try:
        # Agent A: Planner
        out_a, p_a, c_a = call_llm(
            "You are Agent A (Planner). Break the question into "
            "intermediate reasoning steps. Do not give the final answer.",
            f"Question: {question}\nContext: {context}"
        )

        record["steps"].append({
            "agent": "Agent_A",
            "output": out_a
        })

        # Agent B: Solver
        out_b, p_b, c_b = call_llm(
            "You are Agent B (Solver). Use Agent A's plan to solve "
            "the problem carefully and calculate the answer.",
            f"Question: {question}\nPlan from Agent A:\n{out_a}\n"
            f"Context: {context}"
        )

        record["steps"].append({
            "agent": "Agent_B",
            "output": out_b
        })

        # Agent C: Final answer
        out_c, p_c, c_c = call_llm(
            "You are Agent C (Synthesizer). Review the reasoning and "
            "return ONLY the final answer, concisely.",
            f"Question: {question}\nIntermediate steps:\n{out_b}"
        )

        record["steps"].append({
            "agent": "Agent_C",
            "output": out_c
        })

        record["total_prompt_tokens"] = p_a + p_b + p_c
        record["total_completion_tokens"] = c_a + c_b + c_c
        record["final_answer"] = out_c

        # Keep the original baseline's simple matching rule for now.
        # Use a numeric-aware evaluator for the final GSM8K comparison.
        record["is_correct"] = (
            str(task["ground_truth"]).strip().lower()
            in out_c.lower()
        )

    except Exception as e:
        record["error"] = str(e)
        print(f"Task {task['id']} failed: {e}")

    finally:
        record["total_latency"] = round(
            time.perf_counter() - start_time, 3
        )
        save_experiment(record)

    print(
        f"Task {task['id']} | "
        f"Correct: {record['is_correct']} | "
        f"Latency: {record['total_latency']}s | "
        f"Tokens: {record['total_prompt_tokens'] + record['total_completion_tokens']}"
    )

    return record


if __name__ == "__main__":
    test_task = {
        "id": "demo_1",
        "question": (
            "Janet buys 3 packs of stamps. Each pack has 15 stamps. "
            "She gives 10 stamps to her friend. How many stamps "
            "does she have left?"
        ),
        "ground_truth": "35"
    }

    run_baseline_a0(test_task)
