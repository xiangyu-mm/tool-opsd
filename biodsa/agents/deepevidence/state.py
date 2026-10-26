from typing import (
    List,
    Annotated,
    Sequence,
    Dict,
    Any,
    Optional,
)

from pydantic import BaseModel, Field

from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage

from biodsa.agents.state import CodeExecutionResult


# ===================================================================
# Tool provenance models
# ===================================================================

class ToolTraceItem(BaseModel):
    """
    One tool execution recorded in the complete Agent trajectory.
    """

    # Global execution sequence number.
    step: int

    # Agent that requested the tool:
    # - orchestrator
    # - search
    agent: str

    # Tool identity.
    tool_name: str
    tool_call_id: str

    # The tool call that directly triggered this tool call.
    #
    # For the first tool call inside a Search Agent subgraph,
    # this points to the orchestrator's go_search_agent call.
    #
    # For subsequent Search Agent calls, this points to the
    # preceding tool call in the same research path.
    parent_tool_call_id: Optional[str] = None

    # Agent action round in which the tool was requested.
    round: int

    # Original arguments passed to the tool.
    tool_input: Dict[str, Any]

    # Typical values:
    # - pending
    # - success
    # - error
    status: str

    # Complete raw output returned by the tool.
    raw_output: Optional[Any] = None

    # Optional entities discovered or returned by this tool.
    result_entity_names: List[str] = Field(
        default_factory=list
    )

    # Whether this tool call was identified as useful for
    # constructing the final answer.
    used_in_final_answer: bool = False


class ToolSourceRef(BaseModel):
    """
    Reference to a tool call supporting a key finding.
    """

    tool_call_id: str

    # Explanation of why this tool call supports the finding.
    relevance: str = ""


class KeyFinding(BaseModel):
    """
    A concise evidence-grounded finding reported by the
    unified Search Agent.
    """

    finding: str

    # Tool calls that directly support this finding.
    source_tools: List[ToolSourceRef] = Field(
        default_factory=list
    )


class AnswerEvidence(BaseModel):
    """
    Evidence that is relevant to the final answer.
    """

    # Unique identifier for this evidence item.
    evidence_id: str = ""

    # Entity associated with this evidence, such as:
    # - PMID:34431675
    # - NCT01234567
    # - BRCA1
    entity_name: Optional[str] = None

    # Tool calls that produced or fetched this evidence.
    tool_call_ids: List[str] = Field(
        default_factory=list
    )

    # Evidence content used for reasoning.
    relevant_content: str = ""

    # Explanation of why this evidence supports the answer.
    relevance: str = ""


# ===================================================================
# Main orchestrator state
# ===================================================================

class DeepEvidenceAgentState(BaseModel):
    """
    State for the top-level DeepEvidence orchestrator.
    """

    # add_messages ensures that node-returned messages are appended
    # to the existing message sequence.
    messages: Annotated[
        Sequence[BaseMessage],
        add_messages,
    ]

    code_execution_results: List[
        CodeExecutionResult
    ] = Field(
        default_factory=list
    )

    analysis_plan: str = ""

    # Original user query.
    user_query: str = ""

    # Knowledge bases made available by the caller.
    knowledge_bases: List[str] = Field(
        default_factory=list
    )

    # Search targets requested by the orchestrator.
    search_targets: List[str] = Field(
        default_factory=list
    )

    # Requested budget for the current Search Agent invocation.
    search_rounds_budget: int = 0

    # Token accounting across orchestrator and Search Agent calls.
    total_input_tokens: int = 0
    total_output_tokens: int = 0

    # IDs of Search Agent launcher calls.
    subgraph_tool_call_ids: List[str] = Field(
        default_factory=list
    )

    # Number of Search Agent subgraph calls made by the
    # orchestrator.
    current_round: int = 0

    # Total number of orchestrator model calls.
    current_action_round: int = 0

    # Knowledge bases selected for the next Search Agent call.
    subagent_knowledge_bases: List[str] = Field(
        default_factory=list
    )

    # ===============================================================
    # Provenance and trajectory tracking
    # ===============================================================

    # All tool executions across the orchestrator and Search Agents.
    tool_trace: List[ToolTraceItem] = Field(
        default_factory=list
    )

    # Evidence explicitly selected as relevant to the final answer.
    answer_evidence: List[AnswerEvidence] = Field(
        default_factory=list
    )

    # Subset of tool_trace that contributed to the successful
    # evidence path.
    successful_tool_path: List[ToolTraceItem] = Field(
        default_factory=list
    )

    # Key findings summarized by Search Agents.
    # Each finding retains exact supporting tool-call references.
    key_findings: List[KeyFinding] = Field(
        default_factory=list
    )


# ===================================================================
# Unified Search Agent state
# ===================================================================

class SearchAgentState(BaseModel):
    """
    State for the unified biomedical Search Agent.

    This replaces the former BFSAgentState and DFSAgentState.
    The Search Agent repeatedly performs:

        model reasoning
            -> tool execution
            -> model reasoning
            -> ...
            -> report_key_findings

    until it produces a final response or exhausts its round budget.
    """

    # Search Agent conversation history.
    messages: Annotated[
        Sequence[BaseMessage],
        add_messages,
    ]

    # Code execution records produced within this subgraph.
    code_execution_results: List[
        CodeExecutionResult
    ] = Field(
        default_factory=list
    )

    # Focused research target assigned by the orchestrator.
    #
    # The current workflow also places the target in a HumanMessage,
    # but preserving this explicit field makes exported state easier
    # to inspect and supports future extensions.
    search_target: str = ""

    # Knowledge bases available to this Search Agent invocation.
    knowledge_bases: List[str] = Field(
        default_factory=list
    )

    # Token usage generated inside this Search Agent invocation.
    total_input_tokens: int = 0
    total_output_tokens: int = 0

    # Maximum number of Search Agent action rounds.
    action_rounds_budget: int = 0

    # Number of Search Agent model rounds already performed.
    current_round: int = 0

    # ===============================================================
    # Provenance and trajectory tracking
    # ===============================================================

    # Tool executions performed by this Search Agent.
    #
    # After subgraph completion, these records are merged into the
    # top-level DeepEvidenceAgentState.tool_trace.
    tool_trace: List[ToolTraceItem] = Field(
        default_factory=list
    )

    # Structured findings reported by this Search Agent.
    key_findings: List[KeyFinding] = Field(
        default_factory=list
    )

    # ID of the orchestrator's go_search_agent tool call that
    # launched this Search Agent subgraph.
    parent_tool_call_id: Optional[str] = None


# ===================================================================
# Temporary backward-compatibility aliases
# ===================================================================

# These aliases prevent import errors while the remaining project
# files are being migrated from BFS/DFS to the unified Search Agent.
#
# New code should import and use SearchAgentState directly.
#
# Once no project file references BFSAgentState or DFSAgentState,
# these two aliases may be removed.
BFSAgentState = SearchAgentState
DFSAgentState = SearchAgentState
