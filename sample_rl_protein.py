import os
import re
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from openai import OpenAI

from biodsa.agents import DeepEvidenceAgent
from biodsa.agents.deepevidence.dataset_exporter import DatasetExporter
import time


# ===================================================================
# 1. Configuration
# ===================================================================

AGENT_MODEL = "gpt-6-luna"
JUDGE_MODEL = "gpt-6-luna"

# 请替换成新的有效 Key，推荐通过环境变量读取
API_KEY = os.getenv("POIXE_API_KEY", "sk-rADrz1UBhHb5NCUdrlSj39g5r3rplLbZh4GIog3rkvK8WHXK")
BASE_URL = "https://api.poixe.com/v1/"

EXPORT_BASE_DIR = "/home/data4/xiangyu/BioDSA/tutorials/workdir/protein_samples"

# 蛋白质数据集列表
PROTEIN_FILES = [
    {
        "name": "catalytic_activity",
        "path": "/home/data4/xiangyu/dataset/Protein-oriented_Instructions/catalytic_activity.json"
    },
    {
        "name": "general_function",
        "path": "/home/data4/xiangyu/dataset/Protein-oriented_Instructions/general_function.json"
    },
    {
        "name": "protein_function",
        "path": "/home/data4/xiangyu/dataset/Protein-oriented_Instructions/protein_function.json"
    }
]

# 根据你目前后端的工具配置，如果有特有的知识库请填入
KNOWLEDGE_BASES = ["protein"]


# ===================================================================
# 2. Client and Agent Initialization
# ===================================================================

base_client = OpenAI(
    api_key=API_KEY,
    base_url=BASE_URL,
)

agent = DeepEvidenceAgent(
    model_name=AGENT_MODEL,
    api_type="openai",
    api_key=API_KEY,
    base_url=BASE_URL,
    model_kwargs={
        "max_completion_tokens": 5000,
        "thinking": {"type": "disabled"},
        "reasoning_effort": "none",
    },
    subagent_action_rounds_budget=5,
    main_search_rounds_budget=5,
    main_action_rounds_budget=10,
    light_mode=False,
    llm_timeout=120,
)


# ===================================================================
# 3. General Utility Functions
# ===================================================================

def get_next_sample_number(output_dir: str, sample_prefix: str) -> int:
    """
    扫描已有样本目录，返回下一个可用编号。
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    pattern = re.compile(rf"^{re.escape(sample_prefix)}_(\d+)$")
    existing_numbers = []

    for path in output_path.iterdir():
        if not path.is_dir():
            continue
        match = pattern.match(path.name)
        if match:
            existing_numbers.append(int(match.group(1)))

    return max(existing_numbers, default=0) + 1


import time

def llm_judge(prediction: str, reference: str, client: OpenAI, model: str, max_retries: int = 3) -> bool:
    """
    使用大模型作为裁判，判断预测结果是否与参考答案相符。
    加入了空值处理和自动重试机制，防止 API 偶发错误导致正确样本被丢弃。
    """
    if not prediction or not prediction.strip():
        return False

    prompt = f"""You are a biology expert evaluating an AI's prediction of a protein's function.
Please assess if the 'Prediction' reasonably matches the 'Reference'. 
It does not need to be exactly the same string. As long as the core function, catalytic activity, or biological role is consistent and lacks major contradictions, consider it correct.

[Reference]
{reference}

[Prediction]
{prediction}

Answer strictly with a single word: "YES" if it is reasonably correct, or "NO" if it is wrong.
"""
    
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
            )
            
            # 安全地获取 content，防止返回 None
            content = response.choices[0].message.content
            
            if content is None:
                print(f" [Judge Warning] Attempt {attempt + 1}: Received empty response (None) from LLM. Retrying...")
                time.sleep(2)
                continue
                
            answer = content.strip().upper()
            return "YES" in answer
            
        except Exception as exc:
            print(f" [Judge Error] Attempt {attempt + 1} failed: {exc}")
            time.sleep(2)
            
    # 如果重试了 3 次依然失败，才返回 False
    print(" [Judge Error] All retries failed. Returning False.")
    return False


# ===================================================================
# 4. Protein Dataset Processing
# ===================================================================

def process_protein_file(
    task_name: str,
    file_path: str,
    num_samples_needed: int = 500,
) -> None:
    """
    处理单个蛋白质任务文件。
    """
    print(f"\n{'='*60}")
    print(f"Loading dataset: {task_name}")
    print(f"File path: {file_path}")
    print(f"{'='*60}")

    exported_count = 0
    next_sample_number = get_next_sample_number(EXPORT_BASE_DIR, f"protein_{task_name}")

    with open(file_path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as exc:
            print(f"Failed to parse JSON file {file_path}: {exc}")
            return

    for source_row_number, record in enumerate(data):
        if exported_count >= num_samples_needed:
            break

        # 1. 检查是否为训练集
        metadata = record.get("metadata", {})
        split = metadata.get("split", "")
        if split != "train":
            continue

        original_record = DatasetExporter.make_json_safe(record)

        instruction = str(original_record.get("instruction", "")).strip()
        input_seq = str(original_record.get("input", "")).strip()
        ground_truth = str(original_record.get("output", "")).strip()
        protein_accession = metadata.get("protein_accession", f"unknown-{source_row_number}")

        if not instruction or not input_seq or not ground_truth:
            print(f"[{task_name} - row {source_row_number}] Missing critical fields. Skipping.")
            continue

        original_id = f"protein-{task_name}-{protein_accession}"
        original_id = DatasetExporter.make_json_safe(original_id)

        print(f"\n[{task_name} - row {source_row_number}] ID: {original_id}")
        print(f" 🎯 Reference (GT): {ground_truth[:150]}...")
        print(" ⏳ Triggering Agent...")

        # 组合提问 Prompt
        agent_query = f"{instruction}\n\n{input_seq}\n\nPlease analyze this protein and provide a clear, concise functional summary based on the tools you have."

        try:
            execution_results = agent.go(
                agent_query,
                knowledge_bases=KNOWLEDGE_BASES,
            )
        except Exception as exc:
            print(f" ❌ Agent execution failed: {exc}")
            DatasetExporter.cleanup_workdir(agent.workdir)
            continue

        agent_response = execution_results.final_response or ""

        # 使用 LLM 裁判判断对错
        is_correct = llm_judge(
            prediction=agent_response,
            reference=ground_truth,
            client=base_client,
            model=JUDGE_MODEL
        )

        if not is_correct:
            print(" ❌ LLM Judge evaluated the answer as INCORRECT. Skipping export.")
            DatasetExporter.cleanup_workdir(agent.workdir)
            continue

        print(" 🌟 LLM Judge evaluated the answer as CORRECT.")

        sample_id = f"protein_{task_name}_{next_sample_number:04d}"

        problem_meta = {
            "dataset_name": f"Protein_{task_name}",
            "source_file": file_path,
            "source_row_number": source_row_number,
            "original_id": original_id,
            "protein_accession": protein_accession,
            
            "instruction": instruction,
            "input_sequence": input_seq,
            "ground_truth": ground_truth,
            "agent_answer": agent_response,
            
            "agent_model": AGENT_MODEL,
            "judge_model": JUDGE_MODEL,
            "original_record": original_record,
        }

        try:
            DatasetExporter.export_sample(
                execution_results=execution_results,
                user_query=agent_query,
                output_dir=EXPORT_BASE_DIR,
                sample_id=sample_id,
                workdir=agent.workdir,
                clean_workdir_after_export=True,
                problem_meta=problem_meta,
            )
        except Exception as exc:
            print(f" ❌ Export failed: {exc}")
            DatasetExporter.cleanup_workdir(agent.workdir)
            continue

        exported_count += 1
        next_sample_number += 1

        print(f" ✅ Exported RL Sample: {sample_id}")
        print(f" 📈 Progress for {task_name}: {exported_count}/{num_samples_needed}")

    print(f"\n🎉 Finished processing {task_name}. Exported {exported_count} samples.")


# ===================================================================
# 5. Main
# ===================================================================

if __name__ == "__main__":
    Path(EXPORT_BASE_DIR).mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print("Starting Protein Sampling Task...")
    print("=" * 80)

    for file_info in PROTEIN_FILES:
        process_protein_file(
            task_name=file_info["name"],
            file_path=file_info["path"],
            num_samples_needed=500,  # 设定每个文件采样的成功数量
        )

    print("\n✅ All protein datasets processing completed.")