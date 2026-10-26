"""Protein query and analysis tool wrapper for agents."""

import os
import uuid
from typing import Any, List, Optional, Type

from pydantic import BaseModel, Field
from langchain.tools import BaseTool

from biodsa.sandbox.sandbox_interface import ExecutionSandboxWrapper
from biodsa.tool_wrappers.utils import clean_task_name_for_filename


class ProteinQueryInput(BaseModel):
    task_name: str = Field(
        description=(
            "Short description used for the output filename, "
            "e.g. 'analyze protein function'."
        )
    )

    sequence: Optional[str] = Field(
        default=None,
        description=(
            "Protein amino-acid sequence, a single FASTA entry, or a fenced "
            "sequence block. Provide exactly one of sequence or accession."
        ),
    )

    accession: Optional[str] = Field(
        default=None,
        description=(
            "UniProt primary accession for explicit annotation lookup. "
            "Provide exactly one of sequence or accession. "
            "Isoform identifiers are not supported."
        ),
    )

    query: Optional[str] = Field(
        default=None,
        description=(
            "Free-form protein question. For example: identify its function, "
            "retrieve catalytic reactions, analyze cofactors, localization, "
            "GO annotations, or sequence properties."
        ),
    )

    analysis_topics: Optional[List[str]] = Field(
        default=None,
        description=(
            "Requested analyses/report sections: sequence_properties, "
            "homology, function, catalytic_activity, cofactor, pathway, "
            "localization, subunit, regulation, go, reference_features, "
            "domains. Omit for a broad report. "
            "Requesting domains triggers local Pfam scanning. "
            "Unknown topics are reported as capability gaps."
        ),
    )

    task_type: Optional[str] = Field(
        default=None,
        description=(
            "Deprecated compatibility label. No task whitelist is enforced. "
            "For new calls, use query and analysis_topics."
        ),
    )

    allow_online: bool = Field(
        default=True,
        description=(
            "Allow UniProt REST fallback when local annotations are missing."
        ),
    )

    include_pfam: bool = Field(
        default=False,
        description=(
            "Enable local Pfam/HMMER scanning. Requires PFAM_HMM_PATH "
            "and a pressed Pfam HMM database."
        ),
    )

    max_hits: int = Field(
        default=20,
        ge=1,
        le=200,
        description="Maximum DIAMOND Swiss-Prot search hits.",
    )

    max_annotations: int = Field(
        default=8,
        ge=1,
        le=50,
        description="Maximum reference annotation lookups.",
    )

    min_identity: float = Field(
        default=30.0,
        ge=0.0,
        le=100.0,
        description=(
            "Minimum alignment identity percentage for reference annotation "
            "retrieval. This is not a calibrated function-transfer threshold."
        ),
    )

    min_coverage: float = Field(
        default=0.70,
        ge=0.0,
        le=1.0,
        description=(
            "Minimum query and target single-alignment span coverage "
            "for reference annotation retrieval."
        ),
    )

    threads: int = Field(
        default=8,
        ge=1,
        le=64,
        description="Threads for DIAMOND and optional HMMER.",
    )

    timeout: int = Field(
        default=600,
        ge=1,
        le=7200,
        description=(
            "Timeout in seconds for each external analysis program, "
            "not a total tool-call deadline."
        ),
    )


class UnifiedProteinQueryTool(BaseTool):
    name: str = "query_protein"

    description: str = (
        "Queries and analyzes a protein from an amino-acid sequence or "
        "an explicit UniProt accession. Returns sequence-derived properties, "
        "Swiss-Prot homologs, functional annotations, catalytic equations, "
        "EC/Rhea references, cofactors, pathways, localization, GO terms, "
        "reference-protein features, and optional query-sequence Pfam domains. "
        "Accepts free-form questions rather than a fixed task list. "
        "Use analysis_topics to choose analyses; natural-language query alone "
        "does not activate specialized prediction programs. "
        "IMPORTANT: this tool retrieves evidence and computes basic sequence "
        "properties. It does not predict 3D structures, mutation effects, "
        "transmembrane topology, docking, or kinetic parameters. "
        "Homology does not establish exact substrate specificity. "
        "Reference feature positions are not mapped to the query. "
        "Do not invent mechanisms or treat inferred annotations as experiments."
    )

    args_schema: Type[BaseModel] = ProteinQueryInput

    # A project-specific sandbox class need not be serialized by Pydantic.
    sandbox: Any = Field(default=None, exclude=True)

    def __init__(
        self,
        sandbox: Optional[ExecutionSandboxWrapper] = None,
        **kwargs,
    ):
        super().__init__(sandbox=sandbox, **kwargs)

    def _run(
        self,
        task_name: str,
        sequence: Optional[str] = None,
        accession: Optional[str] = None,
        query: Optional[str] = None,
        analysis_topics: Optional[List[str]] = None,
        task_type: Optional[str] = None,
        allow_online: bool = True,
        include_pfam: bool = False,
        max_hits: int = 20,
        max_annotations: int = 8,
        min_identity: float = 30.0,
        min_coverage: float = 0.70,
        threads: int = 8,
        timeout: int = 600,
        context_tool_call_ids: Optional[List[str]] = None,
    ) -> str:
        cleaned_name = (
            clean_task_name_for_filename(task_name)
            or "protein_analysis"
        )

        # Also prevent path components if the project's helper is permissive.
        cleaned_name = os.path.basename(cleaned_name)[:100]
        if cleaned_name in {"", ".", ".."}:
            cleaned_name = "protein_analysis"

        workdir = (
            self.sandbox.get_workdir()
            if self.sandbox
            else os.path.join(os.getcwd(), "workdir")
        )

        if not self.sandbox:
            os.makedirs(workdir, exist_ok=True)

        filename = (
            f"{cleaned_name}_{uuid.uuid4().hex[:12]}.protein.json"
        )
        save_path = os.path.join(workdir, filename)

        parameters = {
            "sequence": sequence,
            "accession": accession,
            "query": query,
            "analysis_topics": analysis_topics,
            "task_type": task_type,
            "save_path": save_path,
            "allow_online": allow_online,
            "include_pfam": include_pfam,
            "max_hits": max_hits,
            "max_annotations": max_annotations,
            "min_identity": min_identity,
            "min_coverage": min_coverage,
            "threads": threads,
            "timeout": timeout,
        }

        if self.sandbox:
            # repr preserves the inputs as Python literals rather than
            # interpolating them as executable statements.
            code = (
                "from biodsa.tools.protein.protein import query_protein\n"
                f"details, output = query_protein(**{parameters!r})\n"
                "print(output)\n"
                "if details['status'] == 'error':\n"
                "    raise SystemExit(1)\n"
            )

            try:
                exit_code, output, _, runtime, peak_memory = (
                    self.sandbox.execute(
                        language="python",
                        code=code,
                    )
                )
            except Exception as exc:
                return (
                    "Protein tool sandbox execution failed: "
                    f"{type(exc).__name__}: {exc}"
                )

            execution_status = (
                "success"
                if exit_code == 0
                else f"failed (exit code {exit_code})"
            )

            return (
                f"### Execution: {execution_status}\n\n"
                f"### Output:\n{output}\n\n"
                f"*Time: {runtime:.2f}s, "
                f"Peak Mem: {peak_memory:.2f}MB*"
            )

        try:
            from biodsa.tools.protein.protein import query_protein

            _, output = query_protein(**parameters)
            return output

        except Exception as exc:
            return (
                "Protein query tool failed: "
                f"{type(exc).__name__}: {exc}"
            )


# Compatibility aliases for code using the previous class names.
ProteinFunctionFetchInput = ProteinQueryInput


class UnifiedProteinFunctionFetchTool(UnifiedProteinQueryTool):
    """Backward-compatible tool name."""

    name: str = "fetch_protein_function"


__all__ = [
    "ProteinQueryInput",
    "UnifiedProteinQueryTool",
    "ProteinFunctionFetchInput",
    "UnifiedProteinFunctionFetchTool",
]