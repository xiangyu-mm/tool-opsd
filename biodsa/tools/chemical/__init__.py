"""Chemical computation and retrieval backend tools."""

from .chemicals import (
    standardize_to_rdkit_mol,
    analyze_functional_groups,
    estimate_nmr_peaks,
    fetch_pubchem_comprehensive,
    fetch_molecule_profile_fast,
    compute_quantum_properties_slow,
    fetch_reaction_conditions_unified,
    fetch_chembl_target_bioactivity,  # <--- 新增的 ChEMBL 检索
)

__all__ = [
    'standardize_to_rdkit_mol',
    'analyze_functional_groups',
    'estimate_nmr_peaks',
    'fetch_pubchem_comprehensive',
    'fetch_molecule_profile_fast',
    'compute_quantum_properties_slow',
    'fetch_reaction_conditions_unified',
    'fetch_chembl_target_bioactivity',
]