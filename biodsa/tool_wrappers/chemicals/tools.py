import os 
from typing import Optional, Type, List 
from pydantic import BaseModel, Field 
from langchain.tools import BaseTool 

from biodsa.sandbox.sandbox_interface import ExecutionSandboxWrapper 
from biodsa.tool_wrappers.utils import clean_task_name_for_filename 

# ===================================================== 
# 1. Fetch Molecule Profile Tool 
# ===================================================== 
class FetchMoleculeProfileInput(BaseModel): 
    task_name: str = Field(description="Short task description. e.g., 'virtual screening', 'check safety'") 
    identifier: str = Field(description="Molecule identifier (SMILES, SELFIES, or common name).") 

class UnifiedMoleculeDetailsFetchTool(BaseTool): 
    name: str = "fetch_molecule_profile" 
    description: str = ( 
        "Quickly calculates all essential physicochemical properties, ADMET descriptors (Lipinski's MW, LogP, HBD, HBA, TPSA, LUMO, HOMO, and so on), "
        "structural functional groups, estimates NMR peaks, and retrieves GHS Safety & Hazards via PubChem API. "
        "CRITICAL: Use this tool for 'virtual screening', checking 'oral availability', evaluating 'NMR peaks', "
        "or identifying 'safety risks / hazards / flammability' of chemicals. Supports IUPAC names and standard SMILES."
    ) 
    args_schema: Type[BaseModel] = FetchMoleculeProfileInput 
    sandbox: ExecutionSandboxWrapper = None 
     
    def __init__(self, sandbox: ExecutionSandboxWrapper = None): 
        super().__init__() 
        self.sandbox = sandbox 
     
    def _run(self, task_name: str, identifier: str, context_tool_call_ids: Optional[List[str]] = None) -> str: 
        cleaned_task_name = clean_task_name_for_filename(task_name) 
        workdir = self.sandbox.get_workdir() if self.sandbox else os.path.join(os.getcwd(), "workdir")
        os.makedirs(workdir, exist_ok=True) 
        save_path = os.path.join(workdir, f"{cleaned_task_name}.json") 
         
        code_template = f"""
from biodsa.tools.chemical.chemicals import fetch_molecule_profile_fast 
details, output = fetch_molecule_profile_fast(identifier={repr(identifier)}, save_path={repr(save_path)}) 
print(output) 
""" 
        if self.sandbox: 
            exit_code, output, _, rt, pm = self.sandbox.execute(language="python", code=code_template) 
            return f"### Executed Code:\n```python\n{code_template}\n```\n\n### Output:\n{output}\n\n*Time: {rt:.2f}s, Peak Mem: {pm:.2f}MB*" 
        else:
            from biodsa.tools.chemical.chemicals import fetch_molecule_profile_fast
            _, output = fetch_molecule_profile_fast(identifier=identifier, save_path=save_path) 
            return f"### Executed Code:\n```python\n{code_template}\n```\n\n### Output:\n{output}" 


# ===================================================== 
# 2. ChEMBL Target & Bioactivity Fetcher Tool
# ===================================================== 
class ChEMBLTargetFetchInput(BaseModel):
    task_name: str = Field(description="Short description. e.g., 'find targets', 'clinical phase'")
    identifier: str = Field(description="Molecule identifier (Name or SMILES).")

class ChEMBLTargetFetchTool(BaseTool):
    name: str = "fetch_bioactivity_and_targets"
    description: str = (
        "Queries the ChEMBL database to find a molecule's biological targets, mechanism of action (Agonist/Antagonist), "
        "and highest clinical trial phase. CRITICAL: Use this specifically when asked about 'targets', 'receptors', or 'drug approval status'."
    )
    args_schema: Type[BaseModel] = ChEMBLTargetFetchInput
    sandbox: ExecutionSandboxWrapper = None

    def __init__(self, sandbox: ExecutionSandboxWrapper = None): 
        super().__init__() 
        self.sandbox = sandbox 

    def _run(self, task_name: str, identifier: str, context_tool_call_ids: Optional[List[str]] = None) -> str: 
        cleaned_task_name = clean_task_name_for_filename(task_name) 
        workdir = self.sandbox.get_workdir() if self.sandbox else os.path.join(os.getcwd(), "workdir")
        os.makedirs(workdir, exist_ok=True) 
        save_path = os.path.join(workdir, f"{cleaned_task_name}_chembl.json") 
         
        code_template = f"""
from biodsa.tools.chemical.chemicals import fetch_chembl_target_bioactivity
details, output = fetch_chembl_target_bioactivity(identifier={repr(identifier)}, save_path={repr(save_path)}) 
print(output) 
""" 
        if self.sandbox: 
            exit_code, output, _, rt, pm = self.sandbox.execute(language="python", code=code_template) 
            return f"### Executed Code:\n```python\n{code_template}\n```\n\n### Output:\n{output}\n\n*Time: {rt:.2f}s, Peak Mem: {pm:.2f}MB*" 
        else:
            from biodsa.tools.chemical.chemicals import fetch_chembl_target_bioactivity
            _, output = fetch_chembl_target_bioactivity(identifier=identifier, save_path=save_path) 
            return f"### Executed Code:\n```python\n{code_template}\n```\n\n### Output:\n{output}" 


# ===================================================== 
# 3. Compute Quantum Properties Tool 
# ===================================================== 
class ComputeQuantumPropertiesInput(BaseModel):
    task_name: str = Field(description="e.g., 'lumo calculation'") 
    smiles: str = Field(description="The exact SMILES/SELFIES string or name of the molecule.")

class QuantumComputationTool(BaseTool):
    name: str = "compute_quantum_mechanics"
    description: str = (
        "Calculates quantum chemical properties like LUMO energy, HOMO energy, and Dipole Moment. "
    )
    args_schema: Type[BaseModel] = ComputeQuantumPropertiesInput
    sandbox: ExecutionSandboxWrapper = None

    def __init__(self, sandbox: ExecutionSandboxWrapper = None): 
        super().__init__() 
        self.sandbox = sandbox 

    def _run(self, task_name: str, smiles: str, context_tool_call_ids: Optional[List[str]] = None) -> str: 
        cleaned_task_name = clean_task_name_for_filename(task_name) 
        workdir = self.sandbox.get_workdir() if self.sandbox else os.path.join(os.getcwd(), "workdir")
        os.makedirs(workdir, exist_ok=True) 
        save_path = os.path.join(workdir, f"{cleaned_task_name}_quantum.json") 
         
        code_template = f"""
from biodsa.tools.chemical.chemicals import compute_quantum_properties_slow
details, output = compute_quantum_properties_slow(smiles={repr(smiles)}, save_path={repr(save_path)}) 
print(output) 
""" 
        if self.sandbox: 
            exit_code, output, _, rt, pm = self.sandbox.execute(language="python", code=code_template) 
            return f"### Executed Code:\n```python\n{code_template}\n```\n\n### Output:\n{output}\n\n*Time: {rt:.2f}s*" 
        else:
            from biodsa.tools.chemical.chemicals import compute_quantum_properties_slow
            _, output = compute_quantum_properties_slow(smiles=smiles, save_path=save_path) 
            return f"### Executed Code:\n```python\n{code_template}\n```\n\n### Output:\n{output}" 


# ===================================================== 
# 4. Fetch Reaction Conditions Tool
# ===================================================== 
class UnifiedReactionConditionsFetchToolInput(BaseModel): 
    task_name: str = Field(
        description=(
            "A short descriptive name for the task, e.g., 'predict product', "
            "'predict yield', 'find solvents', 'reagent prediction', 'reaction time'."
        )
    )
    reaction_smiles: str = Field(
        description=(
            "The chemical input query (SMILES, SELFIES, InChIKey, or IUPAC name). "
            "Supports multiple modes: "
            "1) Full reaction 'Reactants>>Products' for exact matching; "
            "2) Forward prediction 'Reactants>>' or 'Reactants' to search by reactants and find possible products; "
            "3) Retrosynthesis/Condition search '>>Product' or 'Product' to search by target product."
        )
    )
    limit: int = Field(default=5, description="Maximum number of reaction records to return.") 

class UnifiedReactionConditionsFetchTool(BaseTool): 
    name: str = "fetch_reaction_details" 
    
    description: str = (
        "Fetches empirical chemical reaction data from the local ORD patent database. "
        "Retrieves reaction conditions (time, temperature, solvents), experimental yields (yield %), "
        "and specific chemical components (reagents, catalysts, reactants, products). "
        "Handles SMILES, SELFIES, InChIKeys, or IUPAC names automatically. "
        "Supports bidirectional search: "
        "1) Forward Prediction: Given reactants, find likely products, reagents, and conditions. "
        "2) Retrosynthesis / Condition Recommendation: Given target products, find suitable reaction conditions, solvents, and catalysts. "
        "CRITICAL: Use this tool for questions asking 'what product can be formed', "
        "'what solvents/reagents accelerate the reaction', 'usual timeframes and temperature regimes', "
        "'what is the expected yield', or 'ingredients commonly selected'."
    )
    
    args_schema: Type[BaseModel] = UnifiedReactionConditionsFetchToolInput 
    sandbox: Optional[ExecutionSandboxWrapper] = None
     
    def __init__(self, sandbox: Optional[ExecutionSandboxWrapper] = None): 
        super().__init__() 
        self.sandbox = sandbox 
     
    def _run(self, task_name: str, reaction_smiles: str, limit: int = 5, context_tool_call_ids: Optional[List[str]] = None) -> str: 
        cleaned_task_name = clean_task_name_for_filename(task_name) 
        workdir = self.sandbox.get_workdir() if self.sandbox else os.path.join(os.getcwd(), "workdir")
        os.makedirs(workdir, exist_ok=True) 
        save_path = os.path.join(workdir, f"{cleaned_task_name}.json") 
         
        code_template = f"""
from biodsa.tools.chemical.chemicals import fetch_reaction_conditions_unified 
results, output = fetch_reaction_conditions_unified(reaction_smiles={repr(reaction_smiles)}, limit={limit}, save_path={repr(save_path)}) 
print(output) 
""" 
        if self.sandbox: 
            exit_code, output, _, rt, pm = self.sandbox.execute(language="python", code=code_template)
            return f"### Executed Code:\n```python\n{code_template}\n```\n\n### Output:\n{output}\n\n*Time: {rt:.2f}s*" 
        else:
            from biodsa.tools.chemical.chemicals import fetch_reaction_conditions_unified
            _, output = fetch_reaction_conditions_unified(reaction_smiles=reaction_smiles, limit=limit, save_path=save_path) 
            return f"### Executed Code:\n```python\n{code_template}\n```\n\n### Output:\n{output}"