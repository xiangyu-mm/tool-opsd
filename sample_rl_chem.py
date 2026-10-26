import os
import re
import json
import math
import random  # 1. 引入 random 模块
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

# 请替换成新的有效 Key，推荐通过环境变量读取
API_KEY = os.getenv("POIXE_API_KEY", "sk-rADrz1UBhHb5NCUdrlSj39g5r3rplLbZh4GIog3rkvK8WHXK")
BASE_URL = "https://api.poixe.com/v1/"

EXPORT_BASE_DIR = "/home/data4/xiangyu/BioDSA/tutorials/workdir/chemistry_samples"

# 化学数据集路径
CHEMISTRY_FILE = "/home/data4/xiangyu/dataset/text/data_filtered1.jsonl"

KNOWLEDGE_BASES = [
    "chemistry"
]


# ===================================================================
# 2. Client and Agent Initialization
# ===================================================================

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


def parse_agent_chem_answer(response: str) -> str:
    """
    全兼容解析化学 Agent 的最终答案。
    支持格式：
    1. {"answer": ["Ic1ccc2ncccc2c1"]} (标准列表格式)
    2. {"answer": "Ic1ccc2ncccc2c1"}   (单字符串格式)
    3. {"answer": [-0.0341]}           (数字列表格式)
    4. {"answer": -0.0341}             (单数字格式)
    """
    if not response:
        return "unknown"

    # 1. 【优先解析】：提取 JSON 对象并用 json.loads 动态解析
    json_matches = re.findall(r'\{[^{}]*"answer"[^{}]*\}', response, re.DOTALL)
    for jstr in json_matches:
        try:
            data = json.loads(jstr)
            if "answer" in data:
                ans = data["answer"]
                # 如果是列表/数组：{"answer": ["xxx"]}
                if isinstance(ans, list) and len(ans) > 0:
                    return str(ans[0]).strip()
                # 如果是单字符串或数字：{"answer": "xxx"} / {"answer": 123}
                elif isinstance(ans, (str, int, float)):
                    return str(ans).strip()
        except Exception:
            pass

    # 2. 【正则兜底 1】：匹配列表字符串格式 {"answer": ["xxx"]}
    match_arr_str = re.search(r'\{\s*"answer"\s*:\s*\[\s*"([^"]+)"\s*\]\s*\}', response)
    if match_arr_str:
        return match_arr_str.group(1).strip()

    # 3. 【正则兜底 2】：匹配单字符串格式 {"answer": "xxx"}
    match_str = re.search(r'\{\s*"answer"\s*:\s*"([^"]+)"\s*\}', response)
    if match_str:
        return match_str.group(1).strip()

    # 4. 【正则兜底 3】：匹配列表数字格式 {"answer": [123.45]}
    match_arr_num = re.search(r'\{\s*"answer"\s*:\s*\[\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*\]\s*\}', response)
    if match_arr_num:
        return match_arr_num.group(1).strip()

    # 5. 【正则兜底 4】：匹配单数字格式 {"answer": -0.0341}
    match_num = re.search(r'\{\s*"answer"\s*:\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*\}', response)
    if match_num:
        return match_num.group(1).strip()

    return "unknown"


def check_match(agent_ans: str, target: str) -> bool:
    """
    检查 Agent 的答案是否与目标一致。
    支持字符串完全匹配（如 SELFIES）以及浮点数容差匹配（如 LUMO 能量值）。
    """
    agent_ans = agent_ans.strip()
    target = str(target).strip()

    # 1. 精确字符串匹配 (针对 SELFIES 或其他文本)
    if agent_ans == target:
        return True
        
    # 2. 尝试作为浮点数比较 (针对 LUMO 等数值，允许一定误差)
    try:
        val_agent = float(agent_ans)
        val_target = float(target)
        # 允许绝对误差 1e-4，相对误差 1e-3
        return math.isclose(val_agent, val_target, rel_tol=1e-3, abs_tol=1e-4)
    except ValueError:
        pass
        
    return False


# ===================================================================
# 4. Chemistry Dataset Processing (支持随机打乱采样)
# ===================================================================

def process_chemistry(
    num_samples_needed: int = 500,
    seed: Optional[int] = 42,  # 设置种子保证实验可复现，传入 None 则完全随机
) -> None:
    """
    随机筛选满足以下条件的化学样本：
    1. DeepEvidenceAgent 使用工具后回答正确。
    2. 导出完整执行轨迹和原始题目信息。
    """
    file_path = CHEMISTRY_FILE

    print(f"Loading Chemistry dataset from: {file_path}")

    # 1. 一次性读取所有行并记录原始行号 (source_row_number)
    indexed_lines = []
    with open(file_path, "r", encoding="utf-8") as input_file:
        for source_row_number, line in enumerate(input_file):
            line_str = line.strip()
            if line_str:
                indexed_lines.append((source_row_number, line_str))

    total_lines = len(indexed_lines)
    print(f"Total valid samples loaded: {total_lines}")

    # 2. 随机打乱列表
    if seed is not None:
        random.seed(seed)
        print(f"Random seed set to: {seed}")
    
    random.shuffle(indexed_lines)
    print("Dataset shuffled successfully. Starting sampling...\n")

    exported_count = 0
    next_sample_number = get_next_sample_number(EXPORT_BASE_DIR, "chem_sample")

    # 3. 遍历随机打乱后的样本
    for source_row_number, line in indexed_lines:
        if exported_count >= num_samples_needed:
            break

        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            print(f"[Chem - row {source_row_number}] Invalid JSON: {exc}. Skipping.")
            continue

        original_record = DatasetExporter.make_json_safe(row)

        question = str(original_record.get("query", "")).strip()
        ground_truth = str(original_record.get("target", "")).strip()
        filename = str(original_record.get("filename", "unknown_file"))

        if not question or not ground_truth:
            print(f"[Chem - row {source_row_number}] Missing question or target. Skipping.")
            continue

        original_id = f"chem-{filename}-{source_row_number}"
        original_id = DatasetExporter.make_json_safe(original_id)

        print(f"\n[Chem - row {source_row_number}] ID: {original_id}")
        print(f" 🎯 Ground Truth: {ground_truth}")
        print(" ⏳ Triggering Agent...")

        # 题目本身已包含严格输出要求，直接送入 Agent
        agent_query = f"{question}\n\nPlease use your tools to analyze and solve this problem accurately."

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
        agent_ans = parse_agent_chem_answer(agent_response)

        print(f" 🤖 Agent Answer: {agent_ans}")

        # 只有做对了才保留并导出
        if not check_match(agent_ans, ground_truth):
            print(" ❌ Agent failed to predict the correct target. Skipping export.")
            DatasetExporter.cleanup_workdir(agent.workdir)
            continue

        sample_id = f"chembench_sample_{next_sample_number:04d}"

        problem_meta = {
            "dataset_name": "Chemistry_Filter1",
            "source_file": file_path,
            "source_row_number": source_row_number,
            "original_id": original_id,
            
            "question": question,
            "ground_truth": ground_truth,
            "agent_answer": agent_ans,
            "filename": filename,
            
            "agent_model": AGENT_MODEL,
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
        print(f" 📈 Progress: {exported_count}/{num_samples_needed}")

    print(f"\n🎉 Chemistry processing finished. Successfully exported {exported_count} samples.")


# ===================================================================
# 5. Main
# ===================================================================

if __name__ == "__main__":
    Path(EXPORT_BASE_DIR).mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print("Starting Chemistry Random Sampling...")
    print("=" * 80)

    process_chemistry(
        num_samples_needed=500,  # 设定你需要的成功样本数量
        seed=42,                 # 设置随机种子（设为 None 则是不固定的完全随机）
    )