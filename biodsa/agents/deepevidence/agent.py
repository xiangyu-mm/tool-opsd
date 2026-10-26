import os
import shutil
from typing import (
    Literal,
    List,
    Dict,
    Any,
    Optional,
    Set,
)

from langgraph.graph import StateGraph, END
from langchain_core.messages import (
    SystemMessage,
    AIMessage,
    ToolMessage,
    HumanMessage,
)
from langchain_core.runnables import RunnableConfig

from biodsa.agents.base_agent import BaseAgent
from biodsa.tool_wrappers.code_exec_tool import (
    CodeExecutionTool,
)

from biodsa.agents.deepevidence.state import (
    DeepEvidenceAgentState,
    SearchAgentState,
    ToolTraceItem,
    KeyFinding,
)

from biodsa.agents.deepevidence.execution import (
    DeepEvidenceExecutionResults,
)

from biodsa.agents.deepevidence.prompt import (
    ORCHESTRATOR_SYSTEM_PROMPT_TEMPLATE,
    SEARCH_AGENT_SYSTEM_PROMPT_TEMPLATE,
    MEMORY_GRAPH_PROTOCOL_PROMPT,
    SEARCH_ROUNDS_BUDGET_PROMPT,
    ACTION_ROUNDS_BUDGET_PROMPT,
    PUBMED_PAPERS_KB_PROMPT,
    GENE_SET_KB_PROMPT,
    DISEASE_KB_PROMPT,
    DRUG_KB_PROMPT,
    VARIANT_KB_PROMPT,
    CHEMISTRY_TOOLS_PROMPT,
    PROTEIN_KB_PROMPT,
)

from biodsa.agents.deepevidence.orchestrator_tool import (
    create_search_tool,
    ReportKeyFindingsTool,
)

from biodsa.agents.deepevidence.schema import (
    KNOWLEDGE_BASE_TO_TOOLS_MAP,
    KNOWLEDGE_BASE_LIST,
)

from biodsa.utils.render_utils import (
    render_message_colored,
)

from biodsa.memory.graph import (
    AddToGraph,
    RetrieveFromGraph,
    load_graph_data,
)

from biodsa.memory.memory_graph import (
    get_default_memory_graph_cache_dir,
    clear_manager_cache,
)

from biodsa.tool_wrappers.pubmed.tools import (
    FindEntitiesTool,
    FindRelatedEntitiesTool,
)

from biodsa.tool_wrappers.umls.tools import (
    SearchUMLSEntitiesTool,
)

from biodsa.agents.deepevidence.tool_wrappers.genes.tools import (
    UnifiedGeneSearchTool,
)

from biodsa.agents.deepevidence.tool_wrappers.diseases.tools import (
    UnifiedDiseaseSearchTool,
)

from biodsa.agents.deepevidence.tool_wrappers.drugs.tools import (
    UnifiedDrugSearchTool,
)

from biodsa.tool_wrappers.protein.tools import (
    UnifiedProteinQueryTool,
)

class DeepEvidenceAgent(BaseAgent):
    name = "deepevidence"

    small_model_name: str = None
    small_model_kwargs: Dict[str, Any] = None
    small_model_api_type: str = None
    small_model_api_key: str = None
    small_model_endpoint: str = None

    evidence_graph_name: str = "evidence_graph"
    evidence_graph_cache_dir: str = None

    main_search_rounds_budget: int = 2
    main_action_rounds_budget: int = 6
    subagent_action_rounds_budget: int = 2

    def __init__(
        self,
        model_name: str,
        api_type: str,
        api_key: str,
        endpoint: str = None,
        base_url: str = None,
        container_id: str = None,
        model_kwargs: Dict[str, Any] = None,
        small_model_name: str = None,
        small_model_kwargs: Dict[str, Any] = None,
        small_model_api_type: str = None,
        small_model_api_key: str = None,
        small_model_endpoint: str = None,
        evidence_graph_cache_dir: str = None,
        main_search_rounds_budget: int = 2,
        main_action_rounds_budget: int = 6,
        subagent_action_rounds_budget: int = 2,
        light_mode: bool = False,
        llm_timeout: Optional[float] = None,
        **kwargs,
    ):
        super().__init__(
            model_name=model_name,
            api_type=api_type,
            api_key=api_key,
            endpoint=endpoint,
            base_url=base_url,
            container_id=container_id,
            model_kwargs=model_kwargs,
            llm_timeout=llm_timeout,
        )

        if small_model_name is None:
            self.small_model_name = self.model_name
            self.small_model_kwargs = self.model_kwargs
            self.small_model_api_type = self.api_type
            self.small_model_api_key = self.api_key
            self.small_model_endpoint = self.endpoint
        else:
            self.small_model_name = small_model_name
            self.small_model_kwargs = small_model_kwargs
            self.small_model_api_type = small_model_api_type
            self.small_model_api_key = small_model_api_key
            self.small_model_endpoint = small_model_endpoint

        if evidence_graph_cache_dir is None:
            evidence_graph_cache_dir = (
                get_default_memory_graph_cache_dir()
            )

        self.evidence_graph_cache_dir = (
            evidence_graph_cache_dir
        )

        self.main_search_rounds_budget = max(
            1,
            int(main_search_rounds_budget),
        )

        self.main_action_rounds_budget = max(
            1,
            int(main_action_rounds_budget),
        )

        self.subagent_action_rounds_budget = max(
            1,
            int(subagent_action_rounds_budget),
        )

        self.umls_api_key = os.getenv("UMLS_API_KEY")
        self.light_mode = light_mode

        self.agent_graph = self._create_agent_graph()

        # Debug:
        #
        # graph_object = self.agent_graph.get_graph(xray=1)
        # graph_object.draw_mermaid_png(
        #     output_file_path="deepevidence_graph.png",
        #     max_retries=5,
        #     retry_delay=2.0,
        # )
        # graph_object.print_ascii()

    # ==============================================================
    # Search workflow
    # ==============================================================

    def _call_search_workflow(
        self,
        state: DeepEvidenceAgentState,
        config: RunnableConfig,
    ) -> DeepEvidenceAgentState:
        """
        Execute the Search Agent subgraph and merge its tool trace,
        key findings, and token usage into the parent state.
        """

        print("called: search_workflow")

        # ----------------------------------------------------------
        # 1. Find the launcher call
        # ----------------------------------------------------------

        parent_graph_message = state.messages[-1]

        if not isinstance(parent_graph_message, AIMessage):
            raise ValueError(
                "Search workflow must be launched by an AIMessage"
            )

        launcher_tool_call = None

        for tool_call in (
            parent_graph_message.tool_calls or []
        ):
            if tool_call.get("name") == "go_search_agent":
                launcher_tool_call = tool_call
                break

        if launcher_tool_call is None:
            raise ValueError(
                "No go_search_agent tool call found in the "
                "parent graph message"
            )

        subgraph_tool_call_id = launcher_tool_call["id"]
        launcher_args = launcher_tool_call.get("args", {})

        # ----------------------------------------------------------
        # 2. Build Search Agent inputs
        # ----------------------------------------------------------

        search_target = str(
            launcher_args.get("search_target", "")
        ).strip()

        if not search_target:
            search_target = "\n\n".join(
                state.search_targets or []
            ).strip()

        if not search_target:
            raise ValueError(
                "go_search_agent requires a search_target"
            )

        knowledge_bases = launcher_args.get(
            "knowledge_bases",
            state.subagent_knowledge_bases or [],
        )

        if not knowledge_bases:
            knowledge_bases = (
                state.knowledge_bases
                if state.knowledge_bases
                else KNOWLEDGE_BASE_LIST
            )

        knowledge_bases = list(
            dict.fromkeys(knowledge_bases)
        )

        invalid_knowledge_bases = [
            knowledge_base
            for knowledge_base in knowledge_bases
            if knowledge_base not in KNOWLEDGE_BASE_LIST
        ]

        if invalid_knowledge_bases:
            raise ValueError(
                "Unknown Search Agent knowledge bases: "
                f"{invalid_knowledge_bases}. "
                f"Must be selected from "
                f"{KNOWLEDGE_BASE_LIST}"
            )

        requested_budget = launcher_args.get(
            "search_rounds_budget",
            self.subagent_action_rounds_budget,
        )

        try:
            requested_budget = int(requested_budget)
        except (TypeError, ValueError):
            requested_budget = (
                self.subagent_action_rounds_budget
            )

        action_rounds_budget = max(
            1,
            min(
                requested_budget,
                self.subagent_action_rounds_budget,
            ),
        )

        inputs = {
            "messages": [
                HumanMessage(content=search_target)
            ],
            "search_target": search_target,
            "knowledge_bases": knowledge_bases,
            "action_rounds_budget": (
                action_rounds_budget
            ),
            "current_round": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "tool_trace": [],
            "key_findings": [],
            "parent_tool_call_id": (
                subgraph_tool_call_id
            ),
        }

        # ----------------------------------------------------------
        # 3. Run Search Agent
        # ----------------------------------------------------------

        search_outputs = self.search_workflow.invoke(
            inputs,
            config=config,
        )

        # ----------------------------------------------------------
        # 4. Return a ToolMessage to the orchestrator
        # ----------------------------------------------------------

        all_messages = search_outputs.get(
            "messages",
            [],
        )

        if all_messages:
            final_response = getattr(
                all_messages[-1],
                "content",
                "",
            )
        else:
            final_response = (
                "Search Agent completed without a response."
            )

        response = ToolMessage(
            content=str(final_response or ""),
            name="go_search_agent",
            tool_call_id=subgraph_tool_call_id,
        )

        # ----------------------------------------------------------
        # 5. Merge tool trace
        # ----------------------------------------------------------

        search_tool_trace = search_outputs.get(
            "tool_trace",
            [],
        )

        global_tool_trace = list(
            state.tool_trace or []
        )

        global_tool_trace.append(
            ToolTraceItem(
                step=len(global_tool_trace),
                agent="orchestrator",
                tool_name="go_search_agent",
                tool_call_id=subgraph_tool_call_id,
                parent_tool_call_id=None,
                round=state.current_action_round,
                tool_input=launcher_args,
                status="success",
                result_entity_names=[],
                used_in_final_answer=False,
            )
        )

        for search_trace_item in search_tool_trace:
            trace_item = search_trace_item.model_copy(
                deep=True
            )

            trace_item.step = len(global_tool_trace)
            global_tool_trace.append(trace_item)

        # ----------------------------------------------------------
        # 6. Merge key findings
        # ----------------------------------------------------------

        global_key_findings = list(
            state.key_findings or []
        )

        global_key_findings.extend(
            search_outputs.get(
                "key_findings",
                [],
            )
        )

        # ----------------------------------------------------------
        # 7. Token accounting
        # ----------------------------------------------------------

        total_input_tokens = (
            state.total_input_tokens
            + search_outputs.get(
                "total_input_tokens",
                0,
            )
        )

        total_output_tokens = (
            state.total_output_tokens
            + search_outputs.get(
                "total_output_tokens",
                0,
            )
        )

        return {
            "messages": [response],
            "tool_trace": global_tool_trace,
            "key_findings": global_key_findings,
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
        }

    # ==============================================================
    # Graph creation
    # ==============================================================

    def _create_agent_graph(
        self,
        debug: bool = False,
    ):
        """
        Create the Search Agent subgraph and top-level orchestrator.
        """

        # ----------------------------------------------------------
        # Search Agent subgraph
        # ----------------------------------------------------------

        search_workflow = StateGraph(
            SearchAgentState,
            input=SearchAgentState,
            output=SearchAgentState,
        )

        search_workflow.add_node(
            "search_agent_node",
            self._search_agent_node,
        )

        search_workflow.add_node(
            "search_agent_tool_node",
            self._tool_node_for_search_agent,
        )

        search_workflow.add_conditional_edges(
            "search_agent_node",
            self._should_continue_search_agent,
            {
                "search_agent_tool_node":
                    "search_agent_tool_node",
                "end": END,
            },
        )

        search_workflow.add_edge(
            "search_agent_tool_node",
            "search_agent_node",
        )

        search_workflow.set_entry_point(
            "search_agent_node"
        )

        self.search_workflow = (
            search_workflow.compile(
                debug=debug,
                name="search_workflow",
            )
        )

        # ----------------------------------------------------------
        # Orchestrator graph
        # ----------------------------------------------------------

        orchestrator_workflow = StateGraph(
            DeepEvidenceAgentState,
            input=DeepEvidenceAgentState,
            output=DeepEvidenceAgentState,
        )

        orchestrator_workflow.add_node(
            "search_workflow",
            self._call_search_workflow,
        )

        orchestrator_workflow.add_node(
            "orchestrator_node",
            self._orchestrator_agent_node,
        )

        orchestrator_workflow.add_node(
            "tool_node",
            self._tool_node,
        )

        orchestrator_workflow.add_conditional_edges(
            "orchestrator_node",
            self._should_go_which_workflow,
            {
                "search_workflow": "search_workflow",
                "tool_node": "tool_node",
                "end": END,
            },
        )

        orchestrator_workflow.add_edge(
            "tool_node",
            "orchestrator_node",
        )

        orchestrator_workflow.add_edge(
            "search_workflow",
            "orchestrator_node",
        )

        orchestrator_workflow.set_entry_point(
            "orchestrator_node"
        )

        return orchestrator_workflow.compile(
            debug=debug,
            name="orchestrator_workflow",
        )

    # ==============================================================
    # Prompt construction
    # ==============================================================

    def _append_knowledge_base_prompts(
        self,
        system_prompt: str,
        knowledge_bases: List[str] = None,
    ) -> str:
        """
        Append prompts corresponding to the enabled knowledge bases.
        """

        knowledge_bases = knowledge_bases or []

        if "gene" in knowledge_bases:
            system_prompt += GENE_SET_KB_PROMPT

        if "disease" in knowledge_bases:
            system_prompt += DISEASE_KB_PROMPT

        if "drug" in knowledge_bases:
            system_prompt += DRUG_KB_PROMPT

        if "variant" in knowledge_bases:
            system_prompt += VARIANT_KB_PROMPT

        if "pubmed_papers" in knowledge_bases:
            system_prompt += PUBMED_PAPERS_KB_PROMPT

        if "chemistry" in knowledge_bases:
            system_prompt += CHEMISTRY_TOOLS_PROMPT
        
        if "protein" in knowledge_bases:
            system_prompt += PROTEIN_KB_PROMPT

        return system_prompt

    def _build_system_prompt_for_orchestrator_agent(
        self,
        knowledge_bases: List[str] = None,
    ) -> str:
        system_prompt = (
            ORCHESTRATOR_SYSTEM_PROMPT_TEMPLATE.format(
                workdir=self.workdir
            )
        )

        if not self.light_mode:
            system_prompt += MEMORY_GRAPH_PROTOCOL_PROMPT

        return self._append_knowledge_base_prompts(
            system_prompt=system_prompt,
            knowledge_bases=knowledge_bases,
        )

    def _build_system_prompt_for_search_agent(
        self,
        knowledge_bases: List[str] = None,
    ) -> str:
        system_prompt = (
            SEARCH_AGENT_SYSTEM_PROMPT_TEMPLATE.format(
                workdir=self.workdir
            )
        )

        return self._append_knowledge_base_prompts(
            system_prompt=system_prompt,
            knowledge_bases=knowledge_bases,
        )

    # ==============================================================
    # Tool construction
    # ==============================================================

    def _get_tools_for_orchestrator_agent(
        self,
        allowed_knowledge_bases: List[str] = None,
    ):
        """
        Get tools for the orchestrator with dynamically constrained
        knowledge bases.
        """

        if allowed_knowledge_bases is None:
            allowed_knowledge_bases = (
                KNOWLEDGE_BASE_LIST
            )

        search_tool_class = create_search_tool(
            allowed_knowledge_bases=(
                allowed_knowledge_bases
            ),
            maximum_search_rounds=(
                self.subagent_action_rounds_budget
            ),
        )

        tools = [
            search_tool_class(),
            CodeExecutionTool(self.sandbox),
        ]

        if not self.light_mode:
            tools.append(
                RetrieveFromGraph(
                    database_name=(
                        self.evidence_graph_name
                    ),
                    cache_dir=(
                        self.evidence_graph_cache_dir
                    ),
                )
            )

            tools.append(
                AddToGraph(
                    database_name=(
                        self.evidence_graph_name
                    ),
                    cache_dir=(
                        self.evidence_graph_cache_dir
                    ),
                )
            )

        if (
            "pubmed_papers"
            in allowed_knowledge_bases
        ):
            tools.extend([
                FindEntitiesTool(
                    sandbox=self.sandbox
                ),
                FindRelatedEntitiesTool(
                    sandbox=self.sandbox
                ),
            ])

        if "gene" in allowed_knowledge_bases:
            tools.append(
                UnifiedGeneSearchTool(
                    sandbox=self.sandbox
                )
            )

        if "disease" in allowed_knowledge_bases:
            tools.append(
                UnifiedDiseaseSearchTool(
                    sandbox=self.sandbox
                )
            )

        if "drug" in allowed_knowledge_bases:
            tools.append(
                UnifiedDrugSearchTool(
                    sandbox=self.sandbox
                )
            )

        if "protein" in allowed_knowledge_bases:
            tools.append(
                UnifiedProteinQueryTool(
                    sandbox=self.sandbox
                )
            )

        if self.umls_api_key is not None:
            tools.append(
                SearchUMLSEntitiesTool(
                    umls_api_key=self.umls_api_key,
                    sandbox=self.sandbox,
                )
            )

        return tools

    def _get_tools_for_search_agent(
        self,
        knowledge_bases: List[str],
    ):
        """
        Get tools for the Search Agent.
        """

        knowledge_bases = knowledge_bases or []

        kg_tools = []
        initialized_tool_names = set()

        for knowledge_base in knowledge_bases:
            if (
                knowledge_base
                not in KNOWLEDGE_BASE_TO_TOOLS_MAP
            ):
                raise ValueError(
                    "Unknown Search Agent knowledge base: "
                    f"{knowledge_base}"
                )

            for tool_class in (
                KNOWLEDGE_BASE_TO_TOOLS_MAP[
                    knowledge_base
                ]
            ):
                initialized_tool = tool_class(
                    sandbox=self.sandbox
                )

                if (
                    initialized_tool.name
                    in initialized_tool_names
                ):
                    continue

                initialized_tool_names.add(
                    initialized_tool.name
                )

                kg_tools.append(initialized_tool)

        return kg_tools + [
            CodeExecutionTool(self.sandbox),
            ReportKeyFindingsTool(),
        ]

    # ==============================================================
    # Orchestrator context
    # ==============================================================

    def _build_orchestrator_tool_context(
        self,
        state: DeepEvidenceAgentState,
    ) -> str:
        """
        Build compact context for the orchestrator.

        Direct orchestrator tool results are included as previews.
        Search Agent execution details are represented through key
        findings instead of full raw traces.
        """

        if not state.tool_trace and not state.key_findings:
            return ""

        tool_messages = {}

        for message in state.messages:
            if isinstance(message, ToolMessage):
                tool_messages[
                    message.tool_call_id
                ] = message

        lines = []

        orchestrator_items = [
            item
            for item in state.tool_trace
            if (
                item.agent == "orchestrator"
                and item.status == "success"
                and item.tool_name
                != "go_search_agent"
            )
        ]

        if orchestrator_items:
            lines.extend([
                "## Previous Orchestrator Tool Results",
                "",
            ])

            for item in orchestrator_items:
                lines.append(
                    f"- tool_call_id: "
                    f"{item.tool_call_id}"
                )

                lines.append(
                    f"  tool_name: {item.tool_name}"
                )

                lines.append(
                    f"  round: {item.round}"
                )

                message = tool_messages.get(
                    item.tool_call_id
                )

                if message is not None:
                    result_text = str(
                        message.content
                    )

                    max_preview_length = 2000

                    if (
                        len(result_text)
                        > max_preview_length
                    ):
                        result_text = (
                            result_text[
                                :max_preview_length
                            ]
                            + "\n...[truncated]"
                        )

                    lines.append(
                        "  result_preview: "
                        f"{result_text}"
                    )

                lines.append("")

        if state.key_findings:
            lines.extend([
                "## Key Findings from Search Agents",
                "",
                (
                    "Use the exact source tool_call_id(s) "
                    "when referencing supporting evidence."
                ),
                "",
            ])

            for index, finding in enumerate(
                state.key_findings,
                start=1,
            ):
                lines.append(
                    f"- finding_{index}: "
                    f"{finding.finding}"
                )

                source_ids = ", ".join(
                    source.tool_call_id
                    for source in finding.source_tools
                )

                if source_ids:
                    lines.append(
                        "  source_tool_call_ids: "
                        f"{source_ids}"
                    )

                lines.append("")

        return "\n".join(lines)

    # ==============================================================
    # Orchestrator node and routing
    # ==============================================================

    def _orchestrator_agent_node(
        self,
        state: DeepEvidenceAgentState,
        config: RunnableConfig,
    ) -> DeepEvidenceAgentState:
        """
        Execute one orchestrator model round.
        """

        allowed_knowledge_bases = (
            state.knowledge_bases
            if state.knowledge_bases
            else KNOWLEDGE_BASE_LIST
        )

        tools = (
            self._get_tools_for_orchestrator_agent(
                allowed_knowledge_bases
            )
        )

        system_prompt = (
            self._build_system_prompt_for_orchestrator_agent(
                knowledge_bases=(
                    allowed_knowledge_bases
                )
            )
        )

        messages = [
            SystemMessage(content=system_prompt),
        ] + list(state.messages)

        tool_context = (
            self._build_orchestrator_tool_context(
                state=state
            )
        )

        if tool_context:
            messages.append(
                HumanMessage(
                    content=tool_context
                )
            )

        current_round = state.current_round
        current_action_round = (
            state.current_action_round
        )

        search_rounds_budget_prompt = (
            SEARCH_ROUNDS_BUDGET_PROMPT.format(
                current_round=current_round,
                search_rounds_budget=(
                    self.main_search_rounds_budget
                ),
            )
        )

        messages.append(
            HumanMessage(
                content=(
                    search_rounds_budget_prompt
                )
            )
        )

        action_rounds_budget_prompt = (
            ACTION_ROUNDS_BUDGET_PROMPT.format(
                current_round=(
                    current_action_round
                ),
                action_rounds_budget=(
                    self.main_action_rounds_budget
                ),
            )
        )

        messages.append(
            HumanMessage(
                content=(
                    action_rounds_budget_prompt
                )
            )
        )

        response = self._call_model(
            model_name=self.model_name,
            messages=messages,
            tools=tools,
            model_kwargs=self.model_kwargs,
            parallel_tool_calls=False,
            base_url=self.base_url,
        )

        subagent_knowledge_bases: List[str] = []
        search_targets: List[str] = []
        search_rounds_budget = 0

        if response.tool_calls:
            for tool_call in response.tool_calls:
                if (
                    tool_call.get("name")
                    != "go_search_agent"
                ):
                    continue

                tool_args = tool_call.get(
                    "args",
                    {},
                )

                subagent_knowledge_bases.extend(
                    tool_args.get(
                        "knowledge_bases",
                        [],
                    )
                )

                search_target = tool_args.get(
                    "search_target"
                )

                if search_target:
                    search_targets.append(
                        search_target
                    )

                requested_budget = tool_args.get(
                    "search_rounds_budget",
                    self.subagent_action_rounds_budget,
                )

                try:
                    search_rounds_budget = int(
                        requested_budget
                    )
                except (TypeError, ValueError):
                    search_rounds_budget = (
                        self.subagent_action_rounds_budget
                    )

                search_rounds_budget = max(
                    1,
                    min(
                        search_rounds_budget,
                        self.subagent_action_rounds_budget,
                    ),
                )

                current_round += 1

        subagent_knowledge_bases = list(
            dict.fromkeys(
                subagent_knowledge_bases
            )
        )

        search_targets = list(
            dict.fromkeys(search_targets)
        )

        current_action_round += 1

        input_tokens, output_tokens = (
            self._get_input_output_tokens(
                response
            )
        )

        total_input_tokens = (
            state.total_input_tokens
            + input_tokens
        )

        total_output_tokens = (
            state.total_output_tokens
            + output_tokens
        )

        print(
            "Current search round "
            f"(Search Agent calls): "
            f"{current_round}/"
            f"{self.main_search_rounds_budget}"
        )

        print(
            "Current action round "
            f"(orchestrator calls): "
            f"{current_action_round}/"
            f"{self.main_action_rounds_budget}"
        )

        return {
            "messages": [response],
            "subagent_knowledge_bases": (
                subagent_knowledge_bases
            ),
            "search_targets": search_targets,
            "search_rounds_budget": (
                search_rounds_budget
            ),
            "current_round": current_round,
            "current_action_round": (
                current_action_round
            ),
            "total_input_tokens": (
                total_input_tokens
            ),
            "total_output_tokens": (
                total_output_tokens
            ),
        }

    def _should_go_which_workflow(
        self,
        state: DeepEvidenceAgentState,
    ) -> Literal[
        "search_workflow",
        "tool_node",
        "end",
    ]:
        """
        Route the orchestrator response.
        """

        last_message = state.messages[-1]

        if not isinstance(last_message, AIMessage):
            return "end"

        tool_calls = last_message.tool_calls or []

        if not tool_calls:
            return "end"

        for tool_call in tool_calls:
            if (
                tool_call.get("name")
                == "go_search_agent"
            ):
                return "search_workflow"

        return "tool_node"

    # ==============================================================
    # Search Agent node and routing
    # ==============================================================

    def _search_agent_node(
        self,
        state: SearchAgentState,
        config: RunnableConfig,
    ) -> SearchAgentState:
        """
        Execute one Search Agent model round.
        """

        knowledge_bases = (
            state.knowledge_bases or []
        )

        current_round = state.current_round

        action_rounds_budget = max(
            1,
            state.action_rounds_budget,
        )

        system_prompt = (
            self._build_system_prompt_for_search_agent(
                knowledge_bases=knowledge_bases
            )
        )

        messages = [
            SystemMessage(content=system_prompt),
        ] + list(state.messages)

        action_round_budget_prompt = (
            ACTION_ROUNDS_BUDGET_PROMPT.format(
                current_round=current_round,
                action_rounds_budget=(
                    action_rounds_budget
                ),
            )
        )

        messages.append(
            HumanMessage(
                content=action_round_budget_prompt
            )
        )

        tools = self._get_tools_for_search_agent(
            knowledge_bases=knowledge_bases
        )

        response = self._call_model(
            model_name=self.small_model_name,
            api_type=self.small_model_api_type,
            api_key=self.small_model_api_key,
            endpoint=self.small_model_endpoint,
            base_url=self.base_url,
            messages=messages,
            tools=tools,
            model_kwargs=self.small_model_kwargs,
            parallel_tool_calls=False,
        )

        input_tokens, output_tokens = (
            self._get_input_output_tokens(
                response
            )
        )

        total_input_tokens = (
            state.total_input_tokens
            + input_tokens
        )

        total_output_tokens = (
            state.total_output_tokens
            + output_tokens
        )

        current_round += 1

        print(
            "Current round of the Search Agent: "
            f"{current_round}/"
            f"{action_rounds_budget}"
        )

        return {
            "messages": [response],
            "total_input_tokens": (
                total_input_tokens
            ),
            "total_output_tokens": (
                total_output_tokens
            ),
            "current_round": current_round,
        }

    def _should_continue_search_agent(
        self,
        state: SearchAgentState,
    ) -> Literal[
        "search_agent_tool_node",
        "end",
    ]:
        """
        Continue when tools were requested and the action budget has
        not been exceeded.

        The `>` comparison allows the tool requested in the final
        permitted model round to execute. The following model call can
        then summarize the result without making another tool call.
        """

        if not state.messages:
            return "end"

        last_message = state.messages[-1]

        if not isinstance(last_message, AIMessage):
            return "end"

        if not last_message.tool_calls:
            return "end"

        if (
            state.current_round
            > state.action_rounds_budget
        ):
            print(
                "Search Agent action-round budget "
                "exhausted: "
                f"{state.current_round}/"
                f"{state.action_rounds_budget}"
            )
            return "end"

        return "search_agent_tool_node"

    # ==============================================================
    # Orchestrator tool execution
    # ==============================================================

    def _tool_node(
        self,
        state: DeepEvidenceAgentState,
        config: RunnableConfig,
    ) -> DeepEvidenceAgentState:
        """
        Execute regular tools requested by the orchestrator.
        """

        messages = state.messages

        allowed_knowledge_bases = (
            state.knowledge_bases
            if state.knowledge_bases
            else KNOWLEDGE_BASE_LIST
        )

        last_message = messages[-1]

        if not isinstance(last_message, AIMessage):
            return {
                "messages": [],
                "tool_trace": state.tool_trace,
            }

        tool_calls = last_message.tool_calls or []

        if not tool_calls:
            return {
                "messages": [],
                "tool_trace": state.tool_trace,
            }

        parent_tool_call_id = (
            self._get_orchestrator_parent_tool_call_id(
                state=state
            )
        )

        tool_trace = self._record_tool_calls(
            tool_trace=state.tool_trace,
            tool_calls=tool_calls,
            agent_name="orchestrator",
            current_round=(
                state.current_action_round
            ),
            parent_tool_call_id=(
                parent_tool_call_id
            ),
        )

        available_tools = (
            self._get_tools_for_orchestrator_agent(
                allowed_knowledge_bases=(
                    allowed_knowledge_bases
                )
            )
        )

        available_tools_dict = {
            tool.name: tool
            for tool in available_tools
        }

        responses = []

        for tool_call in tool_calls:
            tool_call_id = tool_call["id"]
            tool_name = tool_call["name"]
            tool_input = tool_call.get(
                "args",
                {},
            )

            try:
                if tool_name not in available_tools_dict:
                    raise ValueError(
                        "Orchestrator requested an "
                        "unavailable tool: "
                        f"{tool_name}"
                    )

                called_tool = (
                    available_tools_dict[tool_name]
                )

                tool_output = self._execute_tool(
                    called_tool=called_tool,
                    tool_name=tool_name,
                    tool_input=tool_input,
                    tool_call_id=tool_call_id,
                    agent_name="orchestrator",
                    current_round=(
                        state.current_action_round
                    ),
                    parent_tool_call_id=(
                        parent_tool_call_id
                    ),
                )

                self._update_tool_call_result(
                    tool_trace=tool_trace,
                    tool_call_id=tool_call_id,
                    tool_output=tool_output,
                    status="success",
                )

                response = ToolMessage(
                    content=str(tool_output),
                    name=tool_name,
                    tool_call_id=tool_call_id,
                )

            except Exception as error:
                error_output = (
                    f"Error executing tool "
                    f"{tool_name} with input "
                    f"{tool_input}: {error}"
                )

                self._update_tool_call_result(
                    tool_trace=tool_trace,
                    tool_call_id=tool_call_id,
                    tool_output=error_output,
                    status="error",
                )

                response = ToolMessage(
                    content=error_output,
                    name=tool_name,
                    tool_call_id=tool_call_id,
                )

            responses.append(response)

        return {
            "messages": responses,
            "tool_trace": tool_trace,
        }

    # ==============================================================
    # Search Agent tool execution
    # ==============================================================

    def _tool_node_for_search_agent(
        self,
        state: SearchAgentState,
        config: RunnableConfig,
    ) -> SearchAgentState:
        """
        Execute tools requested by the Search Agent.
        """

        if not state.messages:
            return {
                "messages": [],
                "tool_trace": state.tool_trace,
                "key_findings": state.key_findings,
            }

        last_message = state.messages[-1]

        if not isinstance(last_message, AIMessage):
            return {
                "messages": [],
                "tool_trace": state.tool_trace,
                "key_findings": state.key_findings,
            }

        tool_calls = last_message.tool_calls or []

        if not tool_calls:
            return {
                "messages": [],
                "tool_trace": state.tool_trace,
                "key_findings": state.key_findings,
            }

        parent_tool_call_id = (
            self._get_subagent_parent_tool_call_id(
                state=state
            )
        )

        tool_trace = self._record_tool_calls(
            tool_trace=state.tool_trace,
            tool_calls=tool_calls,
            agent_name="search",
            current_round=state.current_round,
            parent_tool_call_id=(
                parent_tool_call_id
            ),
        )

        available_tools = (
            self._get_tools_for_search_agent(
                knowledge_bases=(
                    state.knowledge_bases
                )
            )
        )

        available_tools_dict = {
            tool.name: tool
            for tool in available_tools
        }

        responses = []

        key_findings = list(
            state.key_findings or []
        )

        for tool_call in tool_calls:
            tool_call_id = tool_call["id"]
            tool_name = tool_call["name"]
            tool_input = tool_call.get(
                "args",
                {},
            )

            try:
                if tool_name not in available_tools_dict:
                    raise ValueError(
                        "Search Agent requested an "
                        "unavailable tool: "
                        f"{tool_name}"
                    )

                called_tool = (
                    available_tools_dict[tool_name]
                )

                tool_output = self._execute_tool(
                    called_tool=called_tool,
                    tool_name=tool_name,
                    tool_input=tool_input,
                    tool_call_id=tool_call_id,
                    agent_name="search",
                    current_round=state.current_round,
                    parent_tool_call_id=(
                        parent_tool_call_id
                    ),
                )

                self._update_tool_call_result(
                    tool_trace=tool_trace,
                    tool_call_id=tool_call_id,
                    tool_output=tool_output,
                    status="success",
                )

                if tool_name == "report_key_findings":
                    reported_findings = (
                        tool_input.get(
                            "key_findings",
                            [],
                        )
                    )

                    key_findings.extend(
                        KeyFinding.model_validate(
                            finding
                        )
                        for finding
                        in reported_findings
                    )

                response_content = (
                    f"{tool_output}\n\n"
                    "## Tool Call Provenance\n"
                    f"tool_name: {tool_name}\n"
                    f"tool_call_id: {tool_call_id}"
                )

                response = ToolMessage(
                    content=response_content,
                    name=tool_name,
                    tool_call_id=tool_call_id,
                )

            except Exception as error:
                error_output = (
                    f"Error executing tool "
                    f"{tool_name} with input "
                    f"{tool_input}: {error}"
                )

                self._update_tool_call_result(
                    tool_trace=tool_trace,
                    tool_call_id=tool_call_id,
                    tool_output=error_output,
                    status="error",
                )

                response = ToolMessage(
                    content=error_output,
                    name=tool_name,
                    tool_call_id=tool_call_id,
                )

            responses.append(response)

        return {
            "messages": responses,
            "tool_trace": tool_trace,
            "key_findings": key_findings,
        }

    # ==============================================================
    # Public execution methods
    # ==============================================================

    def generate(
        self,
        input_query: str,
        knowledge_bases: List[str] = None,
        verbose: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Generate an Agent response.
        """

        assert (
            self.agent_graph is not None
        ), "Agent graph is not set"

        if input_query is None:
            return [{
                "error": "input_query is required"
            }]

        if knowledge_bases is None:
            knowledge_bases = KNOWLEDGE_BASE_LIST

        try:
            all_results = []

            inputs = {
                "messages": [
                    ("user", input_query)
                ],
                "user_query": input_query,
                "knowledge_bases": (
                    knowledge_bases
                ),
            }

            for streamed_chunk in (
                self.agent_graph.stream(
                    inputs,
                    stream_mode=["values"],
                    subgraphs=True,
                    config={
                        "recursion_limit": 100
                    },
                )
            ):
                chunk = streamed_chunk[-1]

                if verbose:
                    last_message = (
                        chunk["messages"][-1]
                    )

                    print(
                        render_message_colored(
                            last_message,
                            show_tool_calls=True,
                        )
                    )

                all_results.append(chunk)

            return all_results

        except Exception as error:
            print(
                "Error streaming response: "
                f"{error}"
            )
            raise

    def go(
        self,
        input_query: str,
        knowledge_bases: List[str] = None,
        verbose: bool = True,
        clear_evidence_graph_cache: bool = True,
        export_dataset_dir: Optional[str] = None,
        sample_id: Optional[str] = None,
    ) -> DeepEvidenceExecutionResults:
        """
        Execute the Agent and return structured results.
        """

        if knowledge_bases is None:
            knowledge_bases = KNOWLEDGE_BASE_LIST
        else:
            for knowledge_base in knowledge_bases:
                if (
                    knowledge_base
                    not in KNOWLEDGE_BASE_LIST
                ):
                    raise ValueError(
                        "Unknown knowledge base: "
                        f"{knowledge_base}. "
                        f"Must be one of "
                        f"{KNOWLEDGE_BASE_LIST}"
                    )

        if clear_evidence_graph_cache:
            if (
                self.evidence_graph_cache_dir
                is None
            ):
                raise ValueError(
                    "evidence_graph_cache_dir "
                    "is not set"
                )

            if os.path.exists(
                self.evidence_graph_cache_dir
            ):
                shutil.rmtree(
                    self.evidence_graph_cache_dir
                )

            os.makedirs(
                self.evidence_graph_cache_dir,
                exist_ok=True,
            )

            clear_manager_cache(
                cache_dir=(
                    self.evidence_graph_cache_dir
                )
            )

        results = self.generate(
            input_query,
            knowledge_bases=knowledge_bases,
            verbose=verbose,
        )

        if not results:
            raise RuntimeError(
                "Agent returned no execution results"
            )

        final_state = results[-1]

        final_messages = final_state.get("messages") or []

        if not final_messages:
            raise RuntimeError(
                "Agent final state does not contain any messages"
            )

        message_history = self._format_messages(
            final_messages
        )

        code_execution_results = (
            self._format_code_execution_results(
                final_state.get("code_execution_results") or []
            )
        )

        total_input_tokens = (
            final_state.get("total_input_tokens") or 0
        )

        total_output_tokens = (
            final_state.get("total_output_tokens") or 0
        )

        final_response = (
            getattr(
                final_messages[-1],
                "content",
                "",
            )
            or ""
        )


        if not self.light_mode:
            evidence_graph_data = load_graph_data(
                context=self.evidence_graph_name,
                cache_dir=(
                    self.evidence_graph_cache_dir
                ),
            )
        else:
            evidence_graph_data = {}

        tool_trace = final_state.get(
            "tool_trace",
            [],
        )

        successful_tool_path = (
            self._get_successful_tool_path(
                tool_trace=tool_trace
            )
        )

        execution_results = (
            DeepEvidenceExecutionResults(
                sandbox=self.sandbox,
                message_history=message_history,
                code_execution_results=(
                    code_execution_results
                ),
                final_response=final_response,
                total_input_tokens=(
                    total_input_tokens
                ),
                total_output_tokens=(
                    total_output_tokens
                ),
                evidence_graph_data=(
                    evidence_graph_data
                ),
                tool_trace=tool_trace,
                successful_tool_path=(
                    successful_tool_path
                ),
            )
        )

        if export_dataset_dir:
            from biodsa.agents.deepevidence.dataset_exporter import (
                DatasetExporter,
            )

            DatasetExporter.export_sample(
                execution_results=(
                    execution_results
                ),
                user_query=input_query,
                output_dir=export_dataset_dir,
                sample_id=sample_id,
                workdir=self.workdir,
            )

        return execution_results

    # ==============================================================
    # Tool trace helpers
    # ==============================================================

    def _record_tool_calls(
        self,
        tool_trace: List[ToolTraceItem],
        tool_calls: List[Dict[str, Any]],
        agent_name: str,
        current_round: int = 0,
        parent_tool_call_id: Optional[str] = None,
    ) -> List[ToolTraceItem]:
        """
        Add pending tool calls to the trace.
        """

        tool_trace = list(tool_trace or [])

        for tool_call in tool_calls:
            tool_name = tool_call["name"]
            tool_call_id = tool_call["id"]
            tool_input = tool_call.get(
                "args",
                {},
            )

            trace_item = ToolTraceItem(
                step=len(tool_trace),
                agent=agent_name,
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                parent_tool_call_id=(
                    parent_tool_call_id
                ),
                round=current_round,
                tool_input=tool_input,
                status="pending",
                result_entity_names=[],
                used_in_final_answer=False,
            )

            tool_trace.append(trace_item)

        return tool_trace

    def _update_tool_call_result(
        self,
        tool_trace: List[Any],
        tool_call_id: str,
        tool_output: Any,
        status: str = "success",
    ) -> List[Any]:
        """
        Update a previously recorded tool call.
        """

        for item in reversed(tool_trace):
            if item.tool_call_id == tool_call_id:
                item.status = status
                item.raw_output = tool_output
                return tool_trace

        raise ValueError(
            "Tool call id not found in tool trace: "
            f"{tool_call_id}"
        )

    def _get_subagent_parent_tool_call_id(
        self,
        state: SearchAgentState,
    ) -> Optional[str]:
        """
        Get the parent execution call for a Search Agent tool.
        """

        if state.tool_trace:
            return (
                state.tool_trace[-1].tool_call_id
            )

        return state.parent_tool_call_id

    def _get_orchestrator_parent_tool_call_id(
        self,
        state: DeepEvidenceAgentState,
    ) -> Optional[str]:
        """
        Get the preceding orchestrator tool call.
        """

        for item in reversed(state.tool_trace):
            if item.agent == "orchestrator":
                return item.tool_call_id

        return None

    def _execute_tool(
        self,
        called_tool,
        tool_name: str,
        tool_input: Dict[str, Any],
        tool_call_id: str,
        agent_name: str,
        current_round: int,
        parent_tool_call_id: Optional[str],
    ):
        """
        Execute a tool and inject provenance when supported.
        """

        if tool_name == "add_to_graph":
            provenance = {
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "agent": agent_name,
                "round": current_round,
                "parent_tool_call_id": (
                    parent_tool_call_id
                ),
            }

            return called_tool._run(
                **tool_input,
                provenance=provenance,
            )

        return called_tool._run(
            **tool_input
        )

    # ==============================================================
    # Successful path recovery
    # ==============================================================

    def _get_successful_tool_path(
        self,
        tool_trace: List[ToolTraceItem],
    ) -> List[ToolTraceItem]:
        """
        Recover the successful research path from the final
        add_to_graph provenance.

        This handles explicit tool dependencies and key findings
        reported by Search Agent subgraphs.
        """

        if not tool_trace:
            return []

        successful_trace = [
            item
            for item in tool_trace
            if item.status == "success"
        ]

        if not successful_trace:
            return []

        trace_by_call_id = {
            item.tool_call_id: item
            for item in successful_trace
        }

        add_to_graph_items = [
            item
            for item in successful_trace
            if (
                item.agent == "orchestrator"
                and item.tool_name
                == "add_to_graph"
            )
        ]

        if not add_to_graph_items:
            successful_trace.sort(
                key=lambda item: item.step
            )
            return successful_trace

        final_add_to_graph = max(
            add_to_graph_items,
            key=lambda item: item.step,
        )

        source_tool_call_ids: Set[str] = set()

        entities = final_add_to_graph.tool_input.get(
            "entities",
            [],
        )

        for entity in entities:
            if not isinstance(entity, dict):
                continue

            for source in entity.get(
                "source_tools",
                [],
            ):
                if (
                    isinstance(source, dict)
                    and source.get("tool_call_id")
                ):
                    source_tool_call_ids.add(
                        source["tool_call_id"]
                    )

        relations = (
            final_add_to_graph.tool_input.get("relations") or []
        )


        for relation in relations:
            if not isinstance(relation, dict):
                continue

            for source in relation.get(
                "source_tools",
                [],
            ):
                if (
                    isinstance(source, dict)
                    and source.get("tool_call_id")
                ):
                    source_tool_call_ids.add(
                        source["tool_call_id"]
                    )

        selected_ids: Set[str] = {
            final_add_to_graph.tool_call_id
        }

        for source_id in source_tool_call_ids:
            current_id = source_id

            while (
                current_id
                and current_id in trace_by_call_id
            ):
                selected_ids.add(current_id)

                current_id = (
                    trace_by_call_id[
                        current_id
                    ].parent_tool_call_id
                )

        launcher_tool_names = {
            "go_search_agent"
        }

        included_launchers = {
            call_id
            for call_id in selected_ids
            if (
                call_id in trace_by_call_id
                and trace_by_call_id[
                    call_id
                ].tool_name
                in launcher_tool_names
            )
        }

        for item in successful_trace:
            if (
                item.tool_name
                != "report_key_findings"
            ):
                continue

            current_id = item.tool_call_id
            temporary_path = []
            belongs_to_selected_launcher = False

            while (
                current_id
                and current_id in trace_by_call_id
            ):
                temporary_path.append(current_id)

                if current_id in included_launchers:
                    belongs_to_selected_launcher = True
                    break

                current_id = (
                    trace_by_call_id[
                        current_id
                    ].parent_tool_call_id
                )

            if belongs_to_selected_launcher:
                selected_ids.update(
                    temporary_path
                )

        successful_path = [
            trace_by_call_id[call_id]
            for call_id in selected_ids
            if call_id in trace_by_call_id
        ]

        successful_path.sort(
            key=lambda item: item.step
        )

        return successful_path
