"""
Tools for the DeepEvidence agent.
"""

from typing import List, Type

from pydantic import BaseModel, Field, field_validator
from langchain_core.tools import BaseTool

from biodsa.agents.deepevidence.schema import (
    KNOWLEDGE_BASE_LIST,
)
from biodsa.agents.deepevidence.state import (
    KeyFinding,
)


def create_search_tool(
    allowed_knowledge_bases: List[str],
    maximum_search_rounds: int,
) -> Type[BaseTool]:
    """
    Create a Search Agent launcher tool with dynamically constrained
    knowledge bases and search-round budget.

    The tool call is intercepted by LangGraph and routed to the
    Search Agent workflow.
    """

    # Remove duplicates while preserving order.
    allowed_knowledge_bases = list(
        dict.fromkeys(allowed_knowledge_bases)
    )

    if not allowed_knowledge_bases:
        raise ValueError(
            "allowed_knowledge_bases must not be empty"
        )

    # Validate the knowledge bases supplied by the caller.
    for knowledge_base in allowed_knowledge_bases:
        if knowledge_base not in KNOWLEDGE_BASE_LIST:
            raise ValueError(
                f"Unknown knowledge base: {knowledge_base}. "
                f"Must be one of {KNOWLEDGE_BASE_LIST}"
            )

    maximum_search_rounds = int(maximum_search_rounds)

    if maximum_search_rounds < 1:
        raise ValueError(
            "maximum_search_rounds must be at least 1"
        )

    class GoSearchAgentToolInput(BaseModel):
        """
        Input schema for the Search Agent launcher.
        """

        search_rounds_budget: int = Field(
            ...,
            ge=1,
            le=maximum_search_rounds,
            description=(
                "The maximum number of action rounds the Search Agent "
                f"can perform. It must be between 1 and "
                f"{maximum_search_rounds}."
            ),
        )

        knowledge_bases: List[str] = Field(
            ...,
            min_length=1,
            description=(
                "The knowledge bases that the Search Agent should use. "
                f"Valid options: {allowed_knowledge_bases}. "
                "Choose only the knowledge bases relevant to the "
                "search target."
            ),
            json_schema_extra={
                "items": {
                    "type": "string",
                    "enum": allowed_knowledge_bases,
                }
            },
        )

        search_target: str = Field(
            ...,
            min_length=1,
            description=(
                "A clear and focused biomedical research objective. "
                "It must specify: "
                "(1) what information or evidence is needed, and "
                "(2) the key entities to investigate, preferably "
                "using standardized names or identifiers. "
                "The target must be concrete enough for the Search "
                "Agent to determine what to search for and when to "
                "stop."
            ),
        )

        @field_validator("knowledge_bases")
        @classmethod
        def validate_knowledge_bases(
            cls,
            value: List[str],
        ) -> List[str]:
            """
            Ensure all requested knowledge bases are available.
            """
            if not value:
                raise ValueError(
                    "At least one knowledge base must be selected"
                )

            invalid_knowledge_bases = [
                knowledge_base
                for knowledge_base in value
                if knowledge_base
                not in allowed_knowledge_bases
            ]

            if invalid_knowledge_bases:
                raise ValueError(
                    "Invalid knowledge bases: "
                    f"{invalid_knowledge_bases}. "
                    "Must be selected from "
                    f"{allowed_knowledge_bases}"
                )

            # Remove duplicates while preserving order.
            return list(dict.fromkeys(value))

        @field_validator("search_target")
        @classmethod
        def validate_search_target(
            cls,
            value: str,
        ) -> str:
            """
            Ensure the search target contains meaningful text.
            """
            value = value.strip()

            if not value:
                raise ValueError(
                    "search_target must not be empty"
                )

            return value

    class GoSearchAgentTool(BaseTool):
        """
        Launch the biomedical Search Agent workflow.
        """

        name: str = "go_search_agent"

        description: str = (
            "Launch a biomedical Search Agent to iteratively search "
            "the selected knowledge bases, inspect relevant evidence, "
            "perform focused follow-up research, and report key "
            "findings with tool provenance. "
            f"Available knowledge bases: {allowed_knowledge_bases}"
        )

        args_schema: Type[BaseModel] = (
            GoSearchAgentToolInput
        )

        def _run(
            self,
            search_rounds_budget: int,
            knowledge_bases: List[str],
            search_target: str,
        ) -> str:
            """
            Return an acknowledgement if the tool is directly run.

            During normal Agent execution, LangGraph intercepts this
            tool call and routes it to the Search Agent workflow.
            """
            return (
                f"Search Agent started on {knowledge_bases} "
                f"with budget {search_rounds_budget}. "
                f"Search target: {search_target}"
            )

    return GoSearchAgentTool


class ReportKeyFindingsInput(BaseModel):
    """
    Input schema for reporting research findings.
    """

    key_findings: List[KeyFinding] = Field(
        ...,
        min_length=1,
        description=(
            "Concise, high-value findings produced by the Search "
            "Agent. Each finding must include the exact "
            "tool_call_id values that directly support it."
        ),
    )


class ReportKeyFindingsTool(BaseTool):
    """
    Record the final key findings produced by the Search Agent.
    """

    name: str = "report_key_findings"

    description: str = (
        "Report the final key findings from the Search Agent. "
        "Each finding must include the exact source tool_call_id "
        "values from tools executed by the Search Agent."
    )

    args_schema: Type[BaseModel] = (
        ReportKeyFindingsInput
    )

    def _run(
        self,
        key_findings: List[KeyFinding],
    ) -> str:
        return "Key findings recorded successfully."
