import os
import json
import math
import shutil
from enum import Enum
from pathlib import Path
from dataclasses import asdict, is_dataclass
from typing import Dict, Any, List, Optional
from datetime import date, time, datetime


class DatasetExporter:
    """
    Export DeepEvidenceAgent execution results and intermediate
    artifacts into a structured dataset folder.

    导出内容包括：

    1. meta.json
    2. final_response.md
    3. message_history.json
    4. evidence_graph.json
    5. tool_trace_full.json
    6. successful_tool_path.json
    7. intermediate_artifacts/
    8. Python 执行历史
    9. sandbox 中产生的物理文件
    """

    # ===============================================================
    # JSON Serialization
    # ===============================================================

    @staticmethod
    def make_json_safe(value: Any) -> Any:
        """
        将常见 Python、Pandas、NumPy、Pydantic 等类型转换成
        json.dump 可以安全处理的对象。
        """
        if value is None:
            return None

        # 基本类型
        if isinstance(value, (str, int, bool)):
            return value

        if isinstance(value, float):
            if math.isnan(value) or math.isinf(value):
                return None
            return value

        # 日期时间
        if isinstance(value, (datetime, date, time)):
            return value.isoformat()

        # 文件路径
        if isinstance(value, Path):
            return str(value)

        # 枚举类型
        if isinstance(value, Enum):
            return DatasetExporter.make_json_safe(value.value)

        # 字节数据
        if isinstance(value, bytes):
            try:
                return value.decode("utf-8")
            except UnicodeDecodeError:
                return value.hex()

        # Dataclass
        if is_dataclass(value) and not isinstance(value, type):
            return DatasetExporter.make_json_safe(asdict(value))

        # Pydantic v2
        if hasattr(value, "model_dump"):
            try:
                return DatasetExporter.make_json_safe(
                    value.model_dump()
                )
            except Exception:
                pass

        # Pydantic v1
        if hasattr(value, "dict") and callable(value.dict):
            try:
                return DatasetExporter.make_json_safe(
                    value.dict()
                )
            except Exception:
                pass

        # 字典
        if isinstance(value, dict):
            return {
                str(key): DatasetExporter.make_json_safe(item)
                for key, item in value.items()
            }

        # 列表、元组、集合
        if isinstance(value, (list, tuple, set)):
            return [
                DatasetExporter.make_json_safe(item)
                for item in value
            ]

        # NumPy array、Pandas Series 等
        if hasattr(value, "tolist"):
            try:
                converted = value.tolist()

                if converted is not value:
                    return DatasetExporter.make_json_safe(
                        converted
                    )
            except Exception:
                pass

        # NumPy scalar
        if hasattr(value, "item"):
            try:
                converted = value.item()

                if converted is not value:
                    return DatasetExporter.make_json_safe(
                        converted
                    )
            except Exception:
                pass

        # 处理 pd.NA、NaT 等
        value_type_module = type(value).__module__
        value_type_name = type(value).__name__

        if (
            value_type_module.startswith("pandas")
            and value_type_name in {
                "NAType",
                "NaTType",
            }
        ):
            return None

        # 处理其他 NaN-like 对象
        try:
            unequal_to_self = value != value

            if isinstance(unequal_to_self, bool):
                if unequal_to_self:
                    return None
        except Exception:
            pass

        # 最终回退
        return str(value)

    @staticmethod
    def _dump_json(
        output_path: Path,
        data: Any,
    ) -> None:
        """
        安全写入 JSON 文件。
        """
        safe_data = DatasetExporter.make_json_safe(data)

        with open(
            output_path,
            "w",
            encoding="utf-8",
        ) as output_file:
            json.dump(
                safe_data,
                output_file,
                indent=2,
                ensure_ascii=False,
                allow_nan=False,
            )

    # ===============================================================
    # Workdir Cleanup
    # ===============================================================

    @staticmethod
    def cleanup_workdir(workdir: str) -> None:
        """
        清理 workdir 中的所有文件和子目录。

        适用于：
        1. Agent 执行失败；
        2. Agent 答案错误；
        3. 导出完成后的清理。
        """
        if not workdir:
            return

        workdir_path = Path(workdir)

        if not workdir_path.exists():
            return

        cleaned_count = 0

        for child_path in workdir_path.iterdir():
            try:
                if child_path.is_dir():
                    shutil.rmtree(child_path)
                else:
                    child_path.unlink()

                cleaned_count += 1

            except Exception as exc:
                print(
                    f"Failed to clean {child_path}: {exc}"
                )

        if cleaned_count > 0:
            print(
                f"🧹 Cleaned {cleaned_count} leftover item(s) "
                f"from workdir: {workdir_path}"
            )

    # ===============================================================
    # Tool Trace Conversion
    # ===============================================================

    @staticmethod
    def _serialize_trace_item(item: Any) -> Dict[str, Any]:
        """
        将 tool trace item 转换成普通字典。
        """
        if hasattr(item, "model_dump"):
            try:
                return DatasetExporter.make_json_safe(
                    item.model_dump()
                )
            except Exception:
                pass

        if hasattr(item, "dict") and callable(item.dict):
            try:
                return DatasetExporter.make_json_safe(
                    item.dict()
                )
            except Exception:
                pass

        if isinstance(item, dict):
            return DatasetExporter.make_json_safe(item)

        if hasattr(item, "__dict__"):
            return DatasetExporter.make_json_safe(
                vars(item)
            )

        return {
            "value": DatasetExporter.make_json_safe(item)
        }

    # ===============================================================
    # Export
    # ===============================================================

    @staticmethod
    def export_sample(
        execution_results: Any,
        user_query: str,
        output_dir: str,
        sample_id: Optional[str] = None,
        workdir: Optional[str] = None,
        clean_workdir_after_export: bool = True,
        problem_meta: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        将一次完整 Agent 执行导出到独立目录。

        Parameters
        ----------
        execution_results:
            DeepEvidenceAgent 的执行结果。

        user_query:
            实际发送给 Agent 的查询。

        output_dir:
            数据集输出根目录。

        sample_id:
            当前样本的唯一 ID。

        workdir:
            Agent 使用的工作目录。

        clean_workdir_after_export:
            导出完成后是否清理 Agent workdir。

        problem_meta:
            原始题目元数据，例如：
            - dataset_name
            - original_id
            - question
            - ground_truth
            - base_llm_answer
            - agent_answer
            - original_record
        """
        if sample_id is None:
            timestamp = datetime.now().strftime(
                "%Y%m%d_%H%M%S_%f"
            )
            sample_id = f"sample_{timestamp}"

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        sample_dir = output_path / sample_id

        # 防止静默覆盖已有样本
        if sample_dir.exists():
            raise FileExistsError(
                f"Sample directory already exists: {sample_dir}"
            )

        artifacts_dir = (
            sample_dir / "intermediate_artifacts"
        )
        py_exec_dir = (
            artifacts_dir / "python_executions"
        )
        sandbox_files_dir = (
            artifacts_dir / "sandbox_files"
        )

        py_exec_dir.mkdir(
            parents=True,
            exist_ok=False,
        )
        sandbox_files_dir.mkdir(
            parents=True,
            exist_ok=False,
        )

        tool_trace = (
            getattr(execution_results, "tool_trace", None)
            or []
        )

        successful_tool_path = (
            getattr(
                execution_results,
                "successful_tool_path",
                None,
            )
            or []
        )

        # -----------------------------------------------------------
        # 1. meta.json
        # -----------------------------------------------------------

        safe_problem_meta = DatasetExporter.make_json_safe(
            problem_meta if problem_meta is not None else {}
        )

        meta_data = {
            "sample_id": sample_id,
            "user_query": user_query,

            # 原始数据集信息位于这里
            "problem_meta": safe_problem_meta,

            # 为方便快速读取，也将部分关键字段放到顶层
            "dataset_name": safe_problem_meta.get(
                "dataset_name"
            ),
            "dataset_split": safe_problem_meta.get(
                "dataset_split"
            ),
            "original_id": safe_problem_meta.get(
                "original_id"
            ),
            "question": safe_problem_meta.get("question"),
            "ground_truth": safe_problem_meta.get(
                "ground_truth"
            ),
            "base_llm_answer": safe_problem_meta.get(
                "base_llm_answer"
            ),
            "agent_answer": safe_problem_meta.get(
                "agent_answer"
            ),

            # 执行统计
            "total_input_tokens": getattr(
                execution_results,
                "total_input_tokens",
                None,
            ),
            "total_output_tokens": getattr(
                execution_results,
                "total_output_tokens",
                None,
            ),
            "total_tool_steps": len(tool_trace),
            "successful_path_steps": len(
                successful_tool_path
            ),

            "timestamp": datetime.now().isoformat(),
        }

        DatasetExporter._dump_json(
            sample_dir / "meta.json",
            meta_data,
        )

        # -----------------------------------------------------------
        # 2. final_response.md
        # -----------------------------------------------------------

        final_response = getattr(
            execution_results,
            "final_response",
            "",
        ) or ""

        with open(
            sample_dir / "final_response.md",
            "w",
            encoding="utf-8",
        ) as output_file:
            output_file.write(str(final_response))

        # -----------------------------------------------------------
        # 3. message_history.json
        # -----------------------------------------------------------

        message_history = getattr(
            execution_results,
            "message_history",
            [],
        )

        DatasetExporter._dump_json(
            sample_dir / "message_history.json",
            message_history,
        )

        # -----------------------------------------------------------
        # 4. evidence_graph.json
        # -----------------------------------------------------------

        evidence_graph_data = getattr(
            execution_results,
            "evidence_graph_data",
            {},
        )

        DatasetExporter._dump_json(
            sample_dir / "evidence_graph.json",
            evidence_graph_data,
        )

        # -----------------------------------------------------------
        # 5. Tool traces
        # -----------------------------------------------------------

        tool_trace_data = [
            DatasetExporter._serialize_trace_item(item)
            for item in tool_trace
        ]

        DatasetExporter._dump_json(
            sample_dir / "tool_trace_full.json",
            tool_trace_data,
        )

        successful_path_data = [
            DatasetExporter._serialize_trace_item(item)
            for item in successful_tool_path
        ]

        DatasetExporter._dump_json(
            sample_dir / "successful_tool_path.json",
            successful_path_data,
        )

        # -----------------------------------------------------------
        # 6. 分类保存原始工具输出
        # -----------------------------------------------------------

        paper_searches: List[Dict[str, Any]] = []
        paper_contents: List[Dict[str, Any]] = []
        entity_searches: List[Dict[str, Any]] = []

        entity_tool_names = {
            "find_entities",
            "find_related_entities",
            "search_umls_entities",
            "unified_gene_search",
            "unified_disease_search",
            "unified_drug_search",
        }

        for item in tool_trace:
            tool_name = getattr(
                item,
                "tool_name",
                None,
            )

            tool_input = getattr(
                item,
                "tool_input",
                None,
            )

            tool_output = getattr(
                item,
                "raw_output",
                None,
            )

            record = {
                "step": getattr(item, "step", None),
                "tool_call_id": getattr(
                    item,
                    "tool_call_id",
                    None,
                ),
                "agent": getattr(item, "agent", None),
                "tool_name": tool_name,
                "input": tool_input,
                "output": tool_output,
            }

            record = DatasetExporter.make_json_safe(record)

            if tool_name == "search_papers":
                paper_searches.append(record)

            elif tool_name == "fetch_paper_content":
                paper_contents.append(record)

            elif tool_name in entity_tool_names:
                entity_searches.append(record)

        if paper_searches:
            DatasetExporter._dump_json(
                artifacts_dir / "paper_searches.json",
                paper_searches,
            )

        if paper_contents:
            DatasetExporter._dump_json(
                artifacts_dir / "paper_contents.json",
                paper_contents,
            )

        if entity_searches:
            DatasetExporter._dump_json(
                artifacts_dir / "entity_searches.json",
                entity_searches,
            )

        # -----------------------------------------------------------
        # 7. Python 执行历史
        # -----------------------------------------------------------

        code_execution_results = getattr(
            execution_results,
            "code_execution_results",
            None,
        )

        if code_execution_results:
            safe_code_results = (
                DatasetExporter.make_json_safe(
                    code_execution_results
                )
            )

            DatasetExporter._dump_json(
                py_exec_dir / "code_execution_history.json",
                safe_code_results,
            )

            for index, code_result in enumerate(
                safe_code_results
            ):
                if not isinstance(code_result, dict):
                    code_result = {
                        "output": str(code_result)
                    }

                code = code_result.get("code", "")
                output = code_result.get("output", "")

                with open(
                    py_exec_dir
                    / f"step_{index:03d}_script.py",
                    "w",
                    encoding="utf-8",
                ) as output_file:
                    output_file.write(str(code or ""))

                with open(
                    py_exec_dir
                    / f"step_{index:03d}_output.log",
                    "w",
                    encoding="utf-8",
                ) as output_file:
                    output_file.write(str(output or ""))

        # -----------------------------------------------------------
        # 8. 同步 sandbox/workdir 文件
        # -----------------------------------------------------------

        target_workdir = workdir

        if target_workdir is None:
            sandbox = getattr(
                execution_results,
                "sandbox",
                None,
            )

            if sandbox is not None:
                target_workdir = getattr(
                    sandbox,
                    "workdir",
                    None,
                )

        if target_workdir:
            target_workdir_path = Path(target_workdir)

            if target_workdir_path.exists():
                copied_items_count = 0

                for source_path in target_workdir_path.iterdir():
                    destination_path = (
                        sandbox_files_dir / source_path.name
                    )

                    try:
                        if source_path.is_dir():
                            shutil.copytree(
                                source_path,
                                destination_path,
                                dirs_exist_ok=True,
                            )
                        else:
                            shutil.copy2(
                                source_path,
                                destination_path,
                            )

                        copied_items_count += 1

                    except Exception as exc:
                        print(
                            f"Failed to copy artifact "
                            f"{source_path}: {exc}"
                        )

                print(
                    f"📦 Synchronized {copied_items_count} "
                    f"artifact item(s) from workdir to "
                    f"{sandbox_files_dir}"
                )

                if clean_workdir_after_export:
                    DatasetExporter.cleanup_workdir(
                        str(target_workdir_path)
                    )

        print(
            f"✅ Successfully exported distillation sample to: "
            f"{sample_dir}"
        )

        return str(sample_dir)
