@echo off
REM Runs the full experiment suite.
REM Model: local Ollama qwen2.5:7b by default, or gpt-4o-mini when .env sets
REM ATBP_BACKEND=openai and OPENAI_API_KEY.
REM Safe to stop and restart: finished work is skipped and LLM calls are cached.
REM Progress is written to logs\injection.log and logs\natural.log.

cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
if not exist logs mkdir logs

REM Results folder name for the active model (e.g. qwen2.5_7b or gpt-4o-mini)
for /f "delims=" %%m in ('.venv\Scripts\python -c "import sys; sys.path.insert(0, '.'); from src.llm_client import model_id; print(model_id().replace(':', '_').replace('/', '_'))"') do set MODEL_DIR=%%m
echo Model folder: %MODEL_DIR%

echo [%date% %time%] Fault-injection experiment (%MODEL_DIR%) >> logs\injection.log
.venv\Scripts\python -u experiments\run_injection.py --problems 40 >> logs\injection.log 2>&1

echo [%date% %time%] Natural GSM8K evaluation (%MODEL_DIR%) >> logs\natural.log
.venv\Scripts\python -u experiments\run_natural.py --n 200 >> logs\natural.log 2>&1

.venv\Scripts\python experiments\analyze.py --injection results\injection\%MODEL_DIR%\cases.jsonl --natural results\natural\%MODEL_DIR%\records.jsonl > logs\summary_%MODEL_DIR%.md 2>&1
echo [%date% %time%] Done >> logs\natural.log
