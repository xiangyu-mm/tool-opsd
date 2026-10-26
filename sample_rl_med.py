import os
import re
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from openai import OpenAI

from biodsa.agents import DeepEvidenceAgent
from biodsa.agents.deepevidence.dataset_exporter import DatasetExporter


# ===================================================================
# 1. Configuration
# ===================================================================

BASE_LLM_MODEL = "qwen-turbo"
AGENT_MODEL = "gpt-6-luna"

# 请替换成新的有效 Key，推荐通过环境变量读取
API_KEY = os.getenv("POIXE_API_KEY", "sk-rADrz1UBhHb5NCUdrlSj39g5r3rplLbZh4GIog3rkvK8WHXK")
BASE_URL = "https://api.poixe.com/v1/"

EXPORT_BASE_DIR = "/home/data4/xiangyu/BioDSA/tutorials/workdir"

PUBMEDQA_FILE = (
    "/home/data4/xiangyu/dataset/pubmedqa/"
    "train-00000-of-0000-all.parquet"
)

MEDXPERTQA_FILE = (
    "/home/data4/xiangyu/dataset/MedXpertQA/test.jsonl"
)

KNOWLEDGE_BASES = [
    "pubmed_papers",
    "disease",
    "drug",
    "clinical_trials",
    "gene",
    "compound",
    "pathway"
]


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

def is_nonempty_value(value: Any) -> bool:
    """
    判断一个值是否可以作为有效 ID 或字段值。
    """
    if value is None:
        return False

    if isinstance(value, str):
        return bool(value.strip())

    try:
        missing = pd.isna(value)

        # pd.isna(list) 可能返回数组，因此只处理标量布尔值
        if isinstance(missing, bool):
            return not missing

        if hasattr(missing, "item"):
            try:
                return not bool(missing.item())
            except Exception:
                pass
    except Exception:
        pass

    return True


def get_first_existing_value(
    record: Dict[str, Any],
    candidates: List[str],
    fallback: Any = None,
) -> Any:
    """
    从多个候选字段中提取第一个有效值。
    """
    for field_name in candidates:
        if field_name not in record:
            continue

        value = record[field_name]

        if is_nonempty_value(value):
            return value

    return fallback


def get_next_sample_number(
    output_dir: str,
    sample_prefix: str,
) -> int:
    """
    扫描已有样本目录，返回下一个可用编号。

    例如已有：
        pubmedqa_sample_001
        pubmedqa_sample_002

    则返回 3。
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    pattern = re.compile(
        rf"^{re.escape(sample_prefix)}_(\d+)$"
    )

    existing_numbers = []

    for path in output_path.iterdir():
        if not path.is_dir():
            continue

        match = pattern.match(path.name)

        if match:
            existing_numbers.append(int(match.group(1)))

    return max(existing_numbers, default=0) + 1


def parse_agent_pubmedqa_answer(response: str) -> str:
    """
    解析 PubMedQA Agent 的最终答案。
    """
    matches = re.findall(
        r"FINAL\s+DECISION\s*:\s*(YES|NO|MAYBE)",
        response or "",
        flags=re.IGNORECASE,
    )

    if not matches:
        return "unknown"

    return matches[-1].lower()


def parse_agent_medxpertqa_answer(response: str) -> str:
    """
    解析 MedXpertQA Agent 的最终选项。
    """
    matches = re.findall(
        r"FINAL\s+ANSWER\s*:\s*([A-J])",
        response or "",
        flags=re.IGNORECASE,
    )

    if not matches:
        return "unknown"

    return matches[-1].upper()


# ===================================================================
# 4. Base LLM Evaluation
# ===================================================================

def get_base_llm_answer(
    prompt: str,
    task_type: str,
) -> str:
    """
    获取 Base LLM 的 zero-shot 答案。
    """
    try:
        response = base_client.chat.completions.create(
            model=BASE_LLM_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            temperature=0.0,
            max_tokens=50,
        )

        content = response.choices[0].message.content or ""
        content = content.strip()

        if task_type == "pubmedqa":
            matches = re.findall(
                r"\b(yes|no|maybe)\b",
                content,
                flags=re.IGNORECASE,
            )

            return matches[-1].lower() if matches else "unknown"

        if task_type == "medxpertqa":
            # 只匹配独立的大写选项字母，降低把冠词 A 当答案的概率
            matches = re.findall(
                r"\b([A-J])\b",
                content,
            )

            return matches[-1].upper() if matches else "unknown"

        raise ValueError(f"Unsupported task_type: {task_type}")

    except Exception as exc:
        print(f"Base LLM Error: {exc}")
        return "error"


# ===================================================================
# 5. PubMedQA Processing
# ===================================================================

def process_pubmedqa(
    num_samples_needed: int = 100,
) -> None:
    """
    筛选满足以下条件的 PubMedQA 样本：

    1. Base LLM 回答错误；
    2. DeepEvidenceAgent 回答正确；
    3. 导出完整执行轨迹和原始题目信息。
    """
    file_path = PUBMEDQA_FILE

    print(f"Loading PubMedQA dataset from: {file_path}")

    df = pd.read_parquet(file_path)

    print(f"Loaded {len(df)} PubMedQA rows.")
    print(f"Columns: {list(df.columns)}")

    exported_count = 0
    next_sample_number = get_next_sample_number(
        EXPORT_BASE_DIR,
        "pubmedqa_sample",
    )

    for source_row_number, (dataframe_index, row) in enumerate(
        df.iterrows()
    ):
        if exported_count >= num_samples_needed:
            break

        original_record = DatasetExporter.make_json_safe(
            row.to_dict()
        )

        question = str(
            original_record.get("question", "")
        ).strip()

        ground_truth = str(
            original_record.get("final_decision", "")
        ).lower().strip()

        if not question:
            print(
                f"[PubMedQA - row {source_row_number}] "
                f"Missing question. Skipping."
            )
            continue

        if ground_truth not in {"yes", "no", "maybe"}:
            print(
                f"[PubMedQA - row {source_row_number}] "
                f"Invalid ground truth: {ground_truth!r}. Skipping."
            )
            continue

        original_id = get_first_existing_value(
            original_record,
            candidates=[
                "pubid",
                "id",
                "question_id",
                "qid",
                "uid",
                "pmid",
            ],
            fallback=f"pubmedqa-train-{source_row_number}",
        )

        original_id = DatasetExporter.make_json_safe(original_id)

        base_prompt = (
            "Answer the following biomedical question with ONLY "
            "'yes', 'no', or 'maybe'. Do not provide explanations.\n\n"
            f"Question: {question}"
        )

        base_ans = get_base_llm_answer(
            base_prompt,
            "pubmedqa",
        )

        print(
            f"[PubMedQA - row {source_row_number}] "
            f"ID: {original_id} | "
            f"GT: {ground_truth} | "
            f"Base LLM: {base_ans}"
        )

        # 仅保留 Base LLM 做错的题目
        if base_ans == ground_truth:
            continue

        print("  -> Base LLM failed. Triggering Agent...")

        agent_query = (
            f"{question}\n\n"
            "Please research this question using your tools. "
            "You MUST conclude your final response with exactly one "
            "of the following lines: "
            "'FINAL DECISION: YES', "
            "'FINAL DECISION: NO', or "
            "'FINAL DECISION: MAYBE'."
        )

        try:
            execution_results = agent.go(
                agent_query,
                knowledge_bases=KNOWLEDGE_BASES,
            )
        except Exception as exc:
            print(f"  ❌ Agent execution failed: {exc}")
            DatasetExporter.cleanup_workdir(agent.workdir)
            continue

        agent_response = execution_results.final_response or ""
        agent_ans = parse_agent_pubmedqa_answer(agent_response)

        print(f"  -> Agent Answer: {agent_ans}")

        if agent_ans != ground_truth:
            print(
                "  ❌ Agent failed or final answer formatting was "
                "incorrect. Skipping export."
            )
            DatasetExporter.cleanup_workdir(agent.workdir)
            continue

        sample_id = (
            f"pubmedqa_sample_{next_sample_number:03d}"
        )

        problem_meta = {
            # 数据来源
            "dataset_name": "PubMedQA",
            "dataset_split": "train",
            "task_type": "yes_no_maybe",
            "source_file": file_path,

            # 原始位置和 ID
            "source_row_number": source_row_number,
            "dataframe_index": DatasetExporter.make_json_safe(
                dataframe_index
            ),
            "original_id": original_id,

            # 题目与答案，单独保存便于后续访问
            "question": question,
            "ground_truth": ground_truth,
            "original_answer": original_record.get(
                "final_decision"
            ),
            "base_llm_answer": base_ans,
            "agent_answer": agent_ans,

            # 模型信息
            "base_llm_model": BASE_LLM_MODEL,
            "agent_model": AGENT_MODEL,

            # PubMedQA 常见字段，单独保存
            "context": original_record.get("context"),
            "long_answer": original_record.get("long_answer"),
            "pubid": original_record.get("pubid"),

            # 完整原始 Parquet 行，确保任何字段都不会丢失
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
            print(f"  ❌ Export failed: {exc}")
            DatasetExporter.cleanup_workdir(agent.workdir)
            continue

        exported_count += 1
        next_sample_number += 1

        print(f"  ✅ Exported RL Sample: {sample_id}")
        print(
            f"  Progress: {exported_count}/"
            f"{num_samples_needed}"
        )

    print(
        f"PubMedQA processing finished. "
        f"Exported {exported_count} samples."
    )


# ===================================================================
# 6. MedXpertQA Processing
# ===================================================================

def process_medxpertqa(
    num_samples_needed: int = 100,
) -> None:
    """
    筛选满足以下条件的 MedXpertQA 样本：

    1. Base LLM 回答错误；
    2. DeepEvidenceAgent 回答正确；
    3. 导出完整执行轨迹和原始题目信息。
    """
    file_path = MEDXPERTQA_FILE

    print(f"Loading MedXpertQA dataset from: {file_path}")

    exported_count = 0
    next_sample_number = get_next_sample_number(
        EXPORT_BASE_DIR,
        "medxpertqa_sample",
    )

    with open(file_path, "r", encoding="utf-8") as input_file:
        for source_row_number, line in enumerate(input_file):
            if exported_count >= num_samples_needed:
                break

            line = line.strip()

            if not line:
                continue

            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                print(
                    f"[MedXpertQA - row {source_row_number}] "
                    f"Invalid JSON: {exc}. Skipping."
                )
                continue

            original_record = DatasetExporter.make_json_safe(row)

            question = str(
                original_record.get("question", "")
            ).strip()

            ground_truth = str(
                original_record.get("label", "")
            ).upper().strip()

            if not question:
                print(
                    f"[MedXpertQA - row {source_row_number}] "
                    "Missing question. Skipping."
                )
                continue

            if not re.fullmatch(r"[A-J]", ground_truth):
                print(
                    f"[MedXpertQA - row {source_row_number}] "
                    f"Invalid ground truth: {ground_truth!r}. "
                    "Skipping."
                )
                continue

            original_id = get_first_existing_value(
                original_record,
                candidates=[
                    "id",
                    "question_id",
                    "qid",
                    "uid",
                    "problem_id",
                    "sample_id",
                    "item_id",
                ],
                fallback=(
                    f"medxpertqa-test-{source_row_number}"
                ),
            )

            original_id = DatasetExporter.make_json_safe(
                original_id
            )

            answer_choices = get_first_existing_value(
                original_record,
                candidates=[
                    "options",
                    "options_dict",
                    "answer_choices",
                    "choices",
                ],
                fallback=None,
            )

            base_prompt = (
                "Answer the following medical multiple-choice "
                "question. Respond with ONLY the single letter of "
                "the correct option, for example A, B, or C.\n\n"
                f"{question}"
            )

            base_ans = get_base_llm_answer(
                base_prompt,
                "medxpertqa",
            )

            print(
                f"[MedXpertQA - row {source_row_number}] "
                f"ID: {original_id} | "
                f"GT: {ground_truth} | "
                f"Base LLM: {base_ans}"
            )

            # 仅保留 Base LLM 做错的题目
            if base_ans == ground_truth:
                continue

            print("  -> Base LLM failed. Triggering Agent...")

            agent_query = (
                f"{question}\n\n"
                "Please research this clinical scenario using your "
                "tools. You MUST conclude your final response with "
                "the exact string 'FINAL ANSWER: [Letter]', for "
                "example: FINAL ANSWER: A."
            )

            # try:
            execution_results = agent.go(
                    agent_query,
                    knowledge_bases=KNOWLEDGE_BASES,
                )
            # except Exception as exc:
            #     print(f"  ❌ Agent execution failed: {exc}")
            #     DatasetExporter.cleanup_workdir(agent.workdir)
            #     continue

            agent_response = execution_results.final_response or ""
            agent_ans = parse_agent_medxpertqa_answer(
                agent_response
            )

            print(f"  -> Agent Answer: {agent_ans}")

            if agent_ans != ground_truth:
                print(
                    "  ❌ Agent failed or final answer formatting "
                    "was incorrect. Skipping export."
                )
                DatasetExporter.cleanup_workdir(agent.workdir)
                continue

            sample_id = (
                f"medxpertqa_sample_{next_sample_number:03d}"
            )

            problem_meta = {
                # 数据来源
                "dataset_name": "MedXpertQA",
                "dataset_split": "test",
                "task_type": "multiple_choice",
                "source_file": file_path,

                # 原始位置和 ID
                "source_row_number": source_row_number,
                "original_id": original_id,

                # 题目和选项
                "question": question,
                "answer_choices": answer_choices,

                # 答案
                "ground_truth": ground_truth,
                "original_answer": original_record.get("label"),
                "base_llm_answer": base_ans,
                "agent_answer": agent_ans,

                # 模型信息
                "base_llm_model": BASE_LLM_MODEL,
                "agent_model": AGENT_MODEL,

                # 完整原始 JSONL 记录
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
                print(f"  ❌ Export failed: {exc}")
                DatasetExporter.cleanup_workdir(agent.workdir)
                continue

            exported_count += 1
            next_sample_number += 1

            print(f"  ✅ Exported RL Sample: {sample_id}")
            print(
                f"  Progress: {exported_count}/"
                f"{num_samples_needed}"
            )

    print(
        f"MedXpertQA processing finished. "
        f"Exported {exported_count} samples."
    )


# ===================================================================
# 7. Main
# ===================================================================

if __name__ == "__main__":
    Path(EXPORT_BASE_DIR).mkdir(
        parents=True,
        exist_ok=True,
    )

    # print("=" * 80)
    # print("Starting PubMedQA Sampling...")
    # print("=" * 80)

    # process_pubmedqa(
    #     num_samples_needed=800,
    # )

    print()
    print("=" * 80)
    print("Starting MedXpertQA Sampling...")
    print("=" * 80)

    process_medxpertqa(
        num_samples_needed=200,
    )
