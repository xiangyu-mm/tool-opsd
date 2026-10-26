from typing import Literal, List, Dict, Any, Type, Optional
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool
import pandas as pd
import json
import re
import os
import math

from biodsa.tools.pubmed.pubmed_api import (
    pubmed_api_get_paper_references,
    fetch_paper_content_by_pmid
)
from biodsa.tools.pubmed.pubtator_api import (
    pubtator_api_fetch_paper_annotations,
    pubtator_api_find_entities,
    pubtator_api_search_papers,
    pubtator_api_find_related_entities,
)
from biodsa.sandbox.sandbox_interface import ExecutionSandboxWrapper
from biodsa.tool_wrappers.utils import clean_task_name_for_filename, run_python_repl

__all__ = [
    "GetPaperReferencesTool",
    "FetchPaperAnnotationsTool",
    "FetchPaperContentTool",
    "FindEntitiesTool",
    "SearchPapersTool",
    "FindRelatedEntitiesTool",
    "GetPaperReferencesToolInput",
    "FetchPaperAnnotationsToolInput",
    "FetchPaperContentToolInput",
    "FindEntitiesToolInput",
    "SearchPapersToolInput",
    "FindRelatedEntitiesToolInput",
]

def _clean_query_for_pubmed(boolean_query_text: str) -> str:
    """
    Clean the query for pubmed search by removing entity type prefixes and replacing underscores with spaces.
    
    Converts patterns like:
    - @CHEMICAL_remdesivir to remdesivir
    - @DISEASE_Polycystic_Ovary_Syndrome to Polycystic Ovary Syndrome
    - @GENE_BRCA1 to BRCA1
    """
    if not boolean_query_text:
        return boolean_query_text
    
    # Step 1: Remove @ENTITYTYPE_ prefix
    cleaned_query = re.sub(r'@[A-Z]+_', '', boolean_query_text)
    
    # Step 2: Replace underscores with spaces
    cleaned_query = cleaned_query.replace('_', ' ')
    
    return cleaned_query

# =====================================================
# Tool 1: Get Paper References
# =====================================================
class GetPaperReferencesToolInput(BaseModel):
    task_name: str = Field(..., description="A less than three word description of what is the search for.")
    pmids: List[str] = Field(..., description="List of PubMed IDs (PMIDs) to get references for.")
    batch_size: int = Field(default=100, description="Number of PMIDs to process in each main batch.")
    mini_batch_size: int = Field(default=20, description="Size of each sub-batch for threading.")
    max_workers: int = Field(default=4, description="Number of threads for concurrent processing.")
    rate_limit: float = Field(default=3.0, description="Maximum requests per second.")

class GetPaperReferencesTool(BaseTool):
    name: str = "get_paper_references"
    description: str = "Get paper references (citations) for a list of PubMed IDs."
    args_schema: Type[BaseModel] = GetPaperReferencesToolInput
    sandbox: ExecutionSandboxWrapper = None
    
    def __init__(self, sandbox: ExecutionSandboxWrapper = None):
        super().__init__()
        self.sandbox = sandbox

    def _run(self, task_name: str, pmids: List[str], batch_size: int = 100, mini_batch_size: int = 20, max_workers: int = 4, rate_limit: float = 3.0, context_tool_call_ids: Optional[List[str]] = None) -> str:
        cleaned_task_name = clean_task_name_for_filename(task_name)
        if self.sandbox is not None:
            workdir = self.sandbox.get_workdir()
        else:
            workdir = os.path.join(os.getcwd(), "workdir")
            os.makedirs(workdir, exist_ok=True)
        tgt_filepath = os.path.join(workdir, f"{cleaned_task_name}.csv")
        
        code_template = f"""
from biodsa.tools.pubmed.pubmed_api import pubmed_api_get_paper_references
import pandas as pd

search_results = pubmed_api_get_paper_references(
    pmids={repr(pmids)}, batch_size={batch_size}, mini_batch_size={mini_batch_size},
    max_workers={max_workers}, rate_limit={rate_limit}
)

search_results_df = pd.DataFrame(search_results)
search_results_df.to_csv('{tgt_filepath}', index=False)
print("The search results are saved at '{tgt_filepath}'")
print(search_results_df.head().to_markdown())
"""
        if self.sandbox is not None:
            exit_code, output, artifacts, running_time, peak_memory = self.sandbox.execute(language="python", code=code_template)
            result = f"### Executed Code:\n```python\n{code_template}\n```\n\n### Output:\n```\n{output}\n```\n\n*Execution time: {running_time:.2f}s, Peak memory: {peak_memory:.2f}MB*"
            if exit_code != 0: result += f"\n\n⚠️ **Warning:** Code exited with non-zero status ({exit_code})"
            return result
        else:
            output = run_python_repl(code_template)
            return f"### Executed Code:\n```python\n{code_template}\n```\n\n### Output:\n```\n{output}\n```\n\n"

# =====================================================
# Helper Function: Extract Relevant Sections with Context
# =====================================================
def extract_relevant_sections(text: str, grep_pattern: str, context_chars: int = 1000) -> List[Dict[str, Any]]:
    if not text or not grep_pattern:
        return []
    matches = []
    try:
        pattern = re.compile(grep_pattern, re.IGNORECASE | re.DOTALL)
        for match in pattern.finditer(text):
            start, end = match.span()
            context_start = max(0, start - context_chars)
            context_end = min(len(text), end + context_chars)

            pre_context = text[context_start:start]
            sentence_breaks = [m.end() for m in re.finditer(r'[.!?]\s+', pre_context)]
            if sentence_breaks: context_start = context_start + sentence_breaks[-1]

            post_context = text[end:context_end]
            sentence_breaks = [m.start() for m in re.finditer(r'[.!?]\s+', post_context)]
            if sentence_breaks: context_end = end + sentence_breaks[0] + 2

            context = text[context_start:context_end].strip()
            matches.append({'matched_text': match.group(0), 'context': context, 'start_pos': start, 'end_pos': end})
    except re.error:
        search_term = grep_pattern.lower()
        text_lower = text.lower()
        start = 0
        while True:
            pos = text_lower.find(search_term, start)
            if pos == -1: break
            end = pos + len(search_term)
            context_start = max(0, pos - context_chars)
            context_end = min(len(text), end + context_chars)

            pre_context = text[context_start:pos]
            sentence_breaks = [m.end() for m in re.finditer(r'[.!?]\s+', pre_context)]
            if sentence_breaks: context_start = context_start + sentence_breaks[-1]

            post_context = text[end:context_end]
            sentence_breaks = [m.start() for m in re.finditer(r'[.!?]\s+', post_context)]
            if sentence_breaks: context_end = end + sentence_breaks[0] + 2

            matches.append({'matched_text': text[pos:end], 'context': text[context_start:context_end].strip(), 'start_pos': pos, 'end_pos': end})
            start = end

    unique_matches = []
    for match in matches:
        is_duplicate = False
        for existing in unique_matches:
            overlap_start = max(match['start_pos'], existing['start_pos'])
            overlap_end = min(match['end_pos'], existing['end_pos'])
            overlap_len = max(0, overlap_end - overlap_start)
            match_len = match['end_pos'] - match['start_pos']
            if overlap_len > 0.8 * match_len:
                is_duplicate = True
                break
        if not is_duplicate: unique_matches.append(match)
    return unique_matches

# =====================================================
# Tool 2: Fetch Paper Content
# =====================================================
class FetchPaperContentToolInput(BaseModel):
    pmid: str = Field(..., description="A single PubMed ID (PMID) to fetch content for.")
    filter_keywords: str = Field(..., description="Keywords or regex pattern to search for and extract from the paper content.")

class FetchPaperContentTool(BaseTool):
    name: str = "fetch_paper_content"
    description: str = "Fetch and extract specific content from a PubMed paper by PMID using keyword/regex filtering."
    args_schema: Type[BaseModel] = FetchPaperContentToolInput
    sandbox: ExecutionSandboxWrapper = None
    
    def __init__(self, sandbox: ExecutionSandboxWrapper = None):
        super().__init__()
        self.sandbox = sandbox

    def _run(self, pmid: str, filter_keywords: str, context_tool_call_ids: Optional[List[str]] = None) -> str:
        code_template = f"""
from biodsa.tools.pubmed.pubmed_api import fetch_paper_content_by_pmid, format_paper_content_output
result = fetch_paper_content_by_pmid({repr(pmid)})
output = format_paper_content_output(result, filter_keywords={repr(filter_keywords)})
print(output)
"""
        if self.sandbox is not None:
            exit_code, output, artifacts, running_time, peak_memory = self.sandbox.execute(language="python", code=code_template)
            result = f"### Executed Code:\n```python\n{code_template}\n```\n\n### Output:\n```\n{output}\n```\n\n*Execution time: {running_time:.2f}s, Peak memory: {peak_memory:.2f}MB*"
            if exit_code != 0: result += f"\n\n⚠️ **Warning:** Code exited with non-zero status ({exit_code})"
            return result
        else:
            output = run_python_repl(code_template)
            return f"### Executed Code:\n```python\n{code_template}\n```\n\n### Output:\n```\n{output}\n```\n\n"

# =====================================================
# Tool 3: Fetch Paper Annotations
# =====================================================
class FetchPaperAnnotationsToolInput(BaseModel):
    pmids: List[str] = Field(..., description="List of PubMed IDs (PMIDs) to fetch annotations for.")
    batch_size: int = Field(default=50)
    max_retries: int = Field(default=3)
    max_requests_per_second: float = Field(default=3.0)

class FetchPaperAnnotationsTool(BaseTool):
    name: str = "fetch_paper_annotations"
    description: str = "Fetch biomedical entity annotations from PubTator3 for a list of PubMed IDs."
    args_schema: Type[BaseModel] = FetchPaperAnnotationsToolInput
    sandbox: ExecutionSandboxWrapper = None
    
    def __init__(self, sandbox: ExecutionSandboxWrapper = None):
        super().__init__()
        self.sandbox = sandbox

    def _run(self, pmids: List[str], batch_size: int = 50, max_retries: int = 3, max_requests_per_second: float = 3.0, context_tool_call_ids: Optional[List[str]] = None) -> str:
        code_template = f"""
from biodsa.tools.pubmed.pubtator_api import pubtator_api_fetch_paper_annotations
import json
search_results = pubtator_api_fetch_paper_annotations(
    pmids={repr(pmids)}, batch_size={batch_size}, max_retries={max_retries}, max_requests_per_second={max_requests_per_second}
)
print(json.dumps(search_results, indent=4))
"""
        if self.sandbox is not None:
            exit_code, output, artifacts, running_time, peak_memory = self.sandbox.execute(language="python", code=code_template)
            result = f"### Executed Code:\n```python\n{code_template}\n```\n\n### Output:\n```\n{output}\n```\n\n*Execution time: {running_time:.2f}s, Peak memory: {peak_memory:.2f}MB*"
            if exit_code != 0: result += f"\n\n⚠️ **Warning:** Code exited with non-zero status ({exit_code})"
            return result
        else:
            output = run_python_repl(code_template)
            return f"### Executed Code:\n```python\n{code_template}\n```\n\n### Output:\n```\n{output}\n```\n\n"

# =====================================================
# Tool 4: Find Entities
# =====================================================
class FindEntitiesToolInput(BaseModel):
    query_text: str = Field(..., description="A single search term (partial entity name) to find entities.")
    concept_type: Optional[Literal["GENE", "DISEASE", "CHEMICAL", "VARIANT", "SPECIES", "CELLLINE"]] = Field(default=None)
    limit: int = Field(default=10)
    max_retries: int = Field(default=3)
    max_requests_per_second: float = Field(default=3.0)

class FindEntitiesTool(BaseTool):
    name: str = "find_entities"
    description: str = "Find and autocomplete biomedical entity names in the PubTator3 database."
    args_schema: Type[BaseModel] = FindEntitiesToolInput
    sandbox: ExecutionSandboxWrapper = None
    
    def __init__(self, sandbox: ExecutionSandboxWrapper = None):
        super().__init__()
        self.sandbox = sandbox

    def _run(self, query_text: str, concept_type: Optional[Literal["GENE", "DISEASE", "CHEMICAL", "VARIANT", "SPECIES", "CELLLINE"]] = None, limit: int = 10, max_retries: int = 3, max_requests_per_second: float = 3.0, context_tool_call_ids: Optional[List[str]] = None) -> str:
        code_template = f"""
from biodsa.tools.pubmed.pubtator_api import pubtator_api_find_entities
import pandas as pd
results = pubtator_api_find_entities(
    query_text={repr(query_text)}, concept_type={repr(concept_type)},
    limit={limit}, max_retries={max_retries}, max_requests_per_second={max_requests_per_second}
)
if len(results) == 0:
    print("No entities found. Please try again with different query.")
else:
    if isinstance(results, pd.DataFrame): print(results.to_markdown())
    else: print("No entities found. Please try again with different query.")
"""
        if self.sandbox is not None:
            exit_code, output, artifacts, running_time, peak_memory = self.sandbox.execute(language="python", code=code_template)
            result = f"### Executed Code:\n```python\n{code_template}\n```\n\n### Output:\n```\n{output}\n```\n\n*Execution time: {running_time:.2f}s, Peak memory: {peak_memory:.2f}MB*"
            if exit_code != 0: result += f"\n\n⚠️ **Warning:** Code exited with non-zero status ({exit_code})"
            return result
        else:
            output = run_python_repl(code_template)
            return f"### Executed Code:\n```python\n{code_template}\n```\n\n### Output:\n```\n{output}\n```\n\n"

# =====================================================
# Tool 5: Search Papers
# =====================================================
class SearchPapersToolInput(BaseModel):
    task_name: str = Field(..., description="A less than three word description of what is the search for")
    boolean_query_text: Optional[str] = Field(
        default=None,
        description=(
            "Boolean query or simple natural language text. "
            "PRO TIP: Simple keyword combinations (e.g., 'FGFR2 methylation birth weight') "
            "often yield BETTER AND MORE RELEVANT RESULTS than overly complex boolean logic with brackets. "
            "You can still use entity IDs (e.g. '@CHEMICAL_remdesivir') if strict matching is required."
        )
    )
    relation_query: Optional[Dict[str, Any]] = Field(default=None)
    top_k: int = Field(default=100, description="Number of top results to return.")
    max_retries: int = Field(default=3)
    max_requests_per_second: float = Field(default=3.0)

class SearchPapersTool(BaseTool):
    name: str = "search_papers"
    description: str = (
        "Search for PubMed articles using keyword queries, boolean queries, or relation-based queries. "
        "PRO TIP: To get the most relevant papers for a specific question, use simple keywords "
        "(like 'FGFR2 methylation birth weight') rather than complex boolean strings. "
        "Returns paper metadata including PMID, title, journal, date, and abstract."
    )
    args_schema: Type[BaseModel] = SearchPapersToolInput
    sandbox: ExecutionSandboxWrapper = None

    def __init__(self, sandbox: ExecutionSandboxWrapper = None):
        super().__init__()
        self.sandbox = sandbox

    def _run(self, task_name: str, boolean_query_text: Optional[str] = None, relation_query: Optional[Dict[str, Any]] = None, top_k: int = 100, max_retries: int = 3, max_requests_per_second: float = 3.0, context_tool_call_ids: Optional[List[str]] = None) -> str:
        cleaned_task_name = clean_task_name_for_filename(task_name)
        if self.sandbox is not None:
            workdir = self.sandbox.get_workdir()
        else:
            workdir = os.path.join(os.getcwd(), "workdir")
            os.makedirs(workdir, exist_ok=True)
        tgt_filepath = os.path.join(workdir, f"{cleaned_task_name}.csv")

        n_pages = math.ceil(top_k / 10)
        n_pages = max(min(n_pages, 100), 1)

        boolean_query_text_for_pubmed = _clean_query_for_pubmed(boolean_query_text)

        # 核心优化：彻底抛弃 Pandas markdown 输出长文本的灾难，采用 Agent 最爱的纯净字典风格输出
        code_template = f"""
from biodsa.tools.pubmed.pubtator_api import pubtator_api_search_papers
from biodsa.tools.pubmed.pubmed_api import pubmed_api_search_papers
import pandas as pd

df_list = []
has_relation_query = {relation_query is not None}

# 1. PubMed Search (Best Relevance Sorting)
if not has_relation_query:
    pmid_df = pubmed_api_search_papers(
        boolean_query_text={repr(boolean_query_text_for_pubmed)},
        top_k={top_k},
    )
    if pmid_df is not None and not pmid_df.empty:
        for col in ["PMID", "Title", "Journal", "Year", "Abstract"]:
            if col not in pmid_df.columns:
                pmid_df[col] = ""
        pmid_df = pmid_df[["PMID", "Title", "Journal", "Year", "Abstract"]]
        df_list.append(pmid_df)

# 2. PubTator3 Search (Entity highlighting, fallback)
pubtator_results = []
for page in range(1, {n_pages} + 1):
    search_results = pubtator_api_search_papers(
        boolean_query_text={repr(boolean_query_text)},
        relation_query={repr(relation_query)},
        page=page,
        max_retries={max_retries},
        max_requests_per_second={max_requests_per_second}
    )
    if search_results is not None and not search_results.empty:
        pubtator_results.append(search_results)
    else:
        break

if pubtator_results:
    pubtator_df = pd.concat(pubtator_results)
    if "Highlighted_Text" in pubtator_df.columns:
        pubtator_df = pubtator_df.rename(columns={{"Highlighted_Text": "Abstract"}})
    
    for col in ["PMID", "Title", "Journal", "Year", "Abstract"]:
        if col not in pubtator_df.columns:
            pubtator_df[col] = ""
    pubtator_df = pubtator_df[["PMID", "Title", "Journal", "Year", "Abstract"]]
    df_list.append(pubtator_df)

# 3. Combine, Deduplicate and Format Clean Output
if df_list:
    final_df = pd.concat(df_list).reset_index(drop=True)
    # Deduplicate by PMID, keeping the first occurrence (which guarantees PubMed relevance is maintained)
    final_df = final_df.drop_duplicates(subset=["PMID"], keep="first")
    
    # Optional: Save to CSV for persistent logging
    final_df.to_csv('{tgt_filepath}', index=False)
    print(f"The search results are saved at '{tgt_filepath}'")
    print(f"Total results found: {{len(final_df)}}\\n")
    print("=" * 80)
    print("TOP RESULTS (Showing up to 15 most relevant):")
    print("=" * 80)
    
    # FORMAT FOR LLM: Clean text layout rather than Markdown table
    for idx, row in final_df.head(15).iterrows():
        pmid = row.get('PMID', 'N/A')
        title = row.get('Title', 'No Title')
        journal = row.get('Journal', 'Unknown')
        year = row.get('Year', 'Unknown')
        abstract = str(row.get('Abstract', 'No Abstract Available'))
        
        # Clean abstract spaces and truncate at 1200 chars to save context window
        abstract = " ".join(abstract.split())
        if len(abstract) > 1200:
            abstract = abstract[:1200] + " ... [Truncated]"
            
        print(f"PMID: {{pmid}}")
        print(f"Title: {{title}}")
        print(f"Source: {{journal}} ({{year}})")
        print(f"Abstract: {{abstract}}")
        print("-" * 80)
else:
    print("No search results found. Please try again with different query. TIP: Try simpler keyword phrases.")
"""
        if self.sandbox is not None:
            exit_code, output, artifacts, running_time, peak_memory = self.sandbox.execute(language="python", code=code_template)
            result = f"### Executed Code:\n```python\n{code_template}\n```\n\n### Output:\n```\n{output}\n```\n\n"
            if exit_code != 0: result += f"\n\n⚠️ **Warning:** Code exited with non-zero status ({exit_code})"
            return result
        else:
            output = run_python_repl(code_template)
            return f"### Executed Code:\n```python\n{code_template}\n```\n\n### Output:\n```\n{output}\n```\n\n"

# =====================================================
# Tool 6: Find Related Entities
# =====================================================
class FindRelatedEntitiesToolInput(BaseModel):
    target_entity: str = Field(..., description="The target entity to find relations for.")
    relation_type: Literal[
        "ASSOCIATE", "CAUSE", "COMPARE", "COTREAT", "DRUG_INTERACT",
        "INHIBIT", "INTERACT", "NEGATIVE_CORRELATE", "POSITIVE_CORRELATE",
        "PREVENT", "STIMULATE", "TREAT", "ANY"
    ] = Field(..., description="Type of relation to search for.")
    related_entity_type: str = Field(..., description="Type or ID of related entities to find.")
    limit: int = Field(default=100)
    max_retries: int = Field(default=3)
    max_requests_per_second: float = Field(default=3.0)

class FindRelatedEntitiesTool(BaseTool):
    name: str = "find_related_entities"
    description: str = "Find entities that have a specific relationship with a target entity using PubTator3 relations API."
    args_schema: Type[BaseModel] = FindRelatedEntitiesToolInput
    sandbox: ExecutionSandboxWrapper = None
    
    def __init__(self, sandbox: ExecutionSandboxWrapper = None):
        super().__init__()
        self.sandbox = sandbox

    def _run(self, target_entity: str, relation_type: str, related_entity_type: str, limit: int = 100, max_retries: int = 3, max_requests_per_second: float = 3.0, context_tool_call_ids: Optional[List[str]] = None) -> str:
        code_template = f"""
from biodsa.tools.pubmed.pubtator_api import pubtator_api_find_related_entities
import pandas as pd

results = pubtator_api_find_related_entities(
    target_entity={repr(target_entity)}, relation_type={repr(relation_type)},
    related_entity_type={repr(related_entity_type)}, limit={limit},
    max_retries={max_retries}, max_requests_per_second={max_requests_per_second}
)

if results is None: print("Failed to fetch related entities. Please try again.")
elif len(results) == 0: print(f"No related entities found. Please try different parameters.")
else:
    if isinstance(results, pd.DataFrame):
        print(f"Found {{len(results)}} related entities:\\n\\n{{results.to_markdown(index=False)}}")
    else:
        print("Unexpected result format. Please try again.")
"""
        if self.sandbox is not None:
            exit_code, output, artifacts, running_time, peak_memory = self.sandbox.execute(language="python", code=code_template)
            result = f"### Executed Code:\n```python\n{code_template}\n```\n\n### Output:\n```\n{output}\n```\n\n*Execution time: {running_time:.2f}s, Peak memory: {peak_memory:.2f}MB*"
            if exit_code != 0: result += f"\n\n⚠️ **Warning:** Code exited with non-zero status ({exit_code})"
            return result
        else:
            output = run_python_repl(code_template)
            return f"### Executed Code:\n```python\n{code_template}\n```\n\n### Output:\n```\n{output}\n```\n\n"