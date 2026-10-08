import os
import time
from dotenv import load_dotenv
from litellm import completion
from litellm.exceptions import RateLimitError
from src.utils.logger import TrajectoryLogger

load_dotenv()

# Switch to gpt-oss-20b for higher TPM allowance on Groq's free tier
MODEL_NAME = "groq/openai/gpt-oss-20b"

def call_llm(system_prompt: str, user_content: str, max_retries: int = 5) -> tuple[str, int, int]:
    for attempt in range(max_retries):
        try:
            response = completion(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                temperature=0.0
            )
            text = response.choices[0].message.content.strip()
            p_tokens = response.usage.prompt_tokens
            c_tokens = response.usage.completion_tokens
            return text, p_tokens, c_tokens
        except (RateLimitError, Exception) as e:
            err_msg = str(e).lower()
            if "rate_limit" in err_msg or "429" in err_msg or "tokens per minute" in err_msg:
                wait_time = (attempt + 1) * 3  # Pauses 3s, 6s, 9s...
                print(f"\n[Rate Limit] TPM ceiling reached. Pausing {wait_time}s before retrying...")
                time.sleep(wait_time)
            else:
                raise e
    raise RuntimeError("Exceeded maximum retries due to persistent rate limiting.")

def run_baseline_a0(task: dict, logger: TrajectoryLogger):
    trace = logger.create_trace_record(task["id"], baseline_type="A0_Sequential")
    question = task["question"]
    context = task.get("context", "")
    
    # --- Agent A: Planner / Initial Reasoner ---
    prompt_a = (
        "You are Agent A (Planner). Break down the following question into intermediate reasoning steps. "
        "Do not compute final numbers or answers yet."
    )
    out_a, p_a, c_a = call_llm(prompt_a, f"Question: {question}\nContext: {context}")
    trace["total_prompt_tokens"] += p_a
    trace["total_completion_tokens"] += c_a
    trace["steps"].append({"agent": "Agent_A", "output": out_a})

    # --- Agent B: Intermediate Solver ---
    prompt_b = (
        "You are Agent B (Solver). Using the plan from Agent A, execute the intermediate steps and calculate "
        "the intermediate logic/facts."
    )
    user_b = f"Question: {question}\nPlan from Agent A:\n{out_a}\nContext: {context}"
    out_b, p_b, c_b = call_llm(prompt_b, user_b)
    trace["total_prompt_tokens"] += p_b
    trace["total_completion_tokens"] += c_b
    trace["steps"].append({"agent": "Agent_B", "output": out_b})

    # --- Agent C: Final Answer Generator ---
    prompt_c = (
        "You are Agent C (Synthesizer). Review the upstream steps and output ONLY the final answer. "
        "Be concise."
    )
    user_c = f"Question: {question}\nIntermediate steps from Agent B:\n{out_b}"
    out_c, p_c, c_c = call_llm(prompt_c, user_c)
    trace["total_prompt_tokens"] += p_c
    trace["total_completion_tokens"] += c_c
    trace["steps"].append({"agent": "Agent_C", "output": out_c})

    trace["final_answer"] = out_c
    trace["is_correct"] = str(task["ground_truth"]).lower() in out_c.lower()
    
    logger.save_trace(trace)
    print(f"Task {task['id']} Finished. Correct: {trace['is_correct']} | Latency: {trace['total_latency']}s")

if __name__ == "__main__":
    test_task = {
        "id": "demo_1",
        "question": "Janet buys 3 packs of stamps. Each pack has 15 stamps. She gives 10 stamps to her friend. How many stamps does she have left?",
        "ground_truth": "35"
    }
    logger = TrajectoryLogger()
    run_baseline_a0(test_task, logger)