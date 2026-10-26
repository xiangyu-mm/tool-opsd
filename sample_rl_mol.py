#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from openai import OpenAI

from biodsa.agents import DeepEvidenceAgent
from biodsa.agents.deepevidence.dataset_exporter import DatasetExporter


# ===================================================================
# 1. Configuration
# ===================================================================

AGENT_MODEL = "gpt-6-luna"
JUDGE_MODEL = "gpt-6-luna"

# 请根据实际情况配置 API Key 和 Base URL
API_KEY = os.getenv("POIXE_API_KEY", "sk-rADrz1UBhHb5NCUdrlSj39g5r3rplLbZh4GIog3rkvK8WHXK")
BASE_URL = "https://api.poixe.com/v1/"

EXPORT_BASE_DIR = "/home/data4/xiangyu/BioDSA/tutorials/workdir/chemistry_samples"

# 化学数据集列表
CHEMISTRY_FILES = [
    {
        "name": "forward_reaction_prediction",
        "path": "/home/data4/xiangyu/dataset/mol-instruct/Molecule-oriented_Instructions/forward_reaction_prediction.json"
    },
    {
        "name": "property_prediction",
        "path": "/home/data4/xiangyu/dataset/mol-instruct/Molecule-oriented_Instructions/property_prediction.json"
    },
    {
        "name": "reagent_prediction",
        "path": "/home/data4/xiangyu/dataset/mol-instruct/Molecule-oriented_Instructions/reagent_prediction.json"
    }
]

# 配置 Agent 使用的知识库/工具链类型
KNOWLEDGE_BASES = ["chemistry"]


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


def llm_judge_chemistry(prediction: str, reference: str, client: OpenAI, model: str, max_retries: int = 3) -> bool:
    """
    针对化学任务的 LLM 裁判。
    评估 Prediction 是否与 Reference 宽容匹配：
    - 支持 SELFIES、SMILES、IUPAC 格式转换后的化学等价性判断。
    - 允许属性预测的合理数值/定性偏差。
    """
    if not prediction or not prediction.strip():
        return False

    prompt = f"""You are a chemistry expert evaluating an AI's prediction against a ground truth reference for a molecular task.
Please assess if the 'Prediction' reasonably matches the 'Reference'.

Evaluation Guidelines:
1. Molecule Representation Leniency: The reference may use SELFIES (e.g., [C][=C]...), SMILES, or IUPAC names. If the AI prediction identifies the correct target molecule, product, or reagent (even if translated into standard SMILES or plain text names), consider it CORRECT.
2. Core Components: For reaction prediction or reagent prediction, as long as the key major products, reactants, or reagents are correctly identified without major chemical errors, consider it CORRECT.
3. Property Prediction: For numerical or qualitative property predictions, consider it CORRECT if the prediction aligns closely with the reference value or description.
4. Formatting: Ignore minor formatting, punctuation, or wrapper differences.

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

    print(" [Judge Error] All retries failed. Returning False.")
    return False


# ===================================================================
# 4. Chemistry Dataset Processing
# ===================================================================

def process_chemistry_file(
    task_name: str,
    file_path: str,
    num_samples_needed: int = 200,
) -> None:
    """
    处理单个化学分子任务文件。
    """
    print(f"\n{'='*60}")
    print(f"Loading dataset: {task_name}")
    print(f"File path: {file_path}")
    print(f"{'='*60}")

    exported_count = 0
    next_sample_number = get_next_sample_number(EXPORT_BASE_DIR, f"chemistry_{task_name}")

    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        return

    with open(file_path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as exc:
            print(f"Failed to parse JSON file {file_path}: {exc}")
            return

    for source_row_number, record in enumerate(data):
        if exported_count >= num_samples_needed:
            break

        # 1. 检查是否为训练集 (split == "train")
        metadata = record.get("metadata", {})
        split = metadata.get("split", "")
        if split != "train":
            continue

        original_record = DatasetExporter.make_json_safe(record)

        instruction = str(original_record.get("instruction", "")).strip()
        input_seq = str(original_record.get("input", "")).strip()
        ground_truth = str(original_record.get("output", "")).strip()

        if not instruction or not ground_truth:
            print(f"[{task_name} - row {source_row_number}] Missing instruction or output. Skipping.")
            continue

        original_id = f"chemistry-{task_name}-{source_row_number}"
        original_id = DatasetExporter.make_json_safe(original_id)

        print(f"\n[{task_name} - row {source_row_number}] ID: {original_id}")
        print(f" 🎯 Reference (GT): {ground_truth[:150]}...")
        print(" ⏳ Triggering Agent...")

        # 组合提问 Prompt
        if input_seq:
            agent_query = f"{instruction}\n\nInput: {input_seq}\n\nPlease analyze this chemical task and provide a clear, precise answer."
        else:
            agent_query = f"{instruction}\n\nPlease analyze this chemical task and provide a clear, precise answer."

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

        # 使用宽容度 LLM 裁判判断对错
        is_correct = llm_judge_chemistry(
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

        sample_id = f"chemistry_{task_name}_{next_sample_number:04d}"

        problem_meta = {
            "dataset_name": f"Chemistry_{task_name}",
            "source_file": file_path,
            "source_row_number": source_row_number,
            "original_id": original_id,
            "task_type": metadata.get("task", task_name),
            
            "instruction": instruction,
            "input": input_seq,
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
    print("Starting Chemistry Sampling Task...")
    print("=" * 80)

    for file_info in CHEMISTRY_FILES:
        process_chemistry_file(
            task_name=file_info["name"],
            file_path=file_info["path"],
            num_samples_needed=200,  # 设定每个文件采样的成功数量为 200
        )

    print("\n✅ All chemistry datasets processing completed.")