"""General protein query and analysis backend."""

from .protein import (
    TOOL_VERSION,
    SUPPORTED_ANALYSIS_TOPICS,
    build_protein_annotation_index,
    compute_sequence_properties,
    fetch_protein_function_unified,
    format_protein_report,
    get_database_fingerprint,
    load_local_annotation,
    normalize_sequence,
    query_protein,
    scan_pfam,
    search_swissprot,
)

__all__ = [
    "TOOL_VERSION",
    "SUPPORTED_ANALYSIS_TOPICS",
    "build_protein_annotation_index",
    "compute_sequence_properties",
    "fetch_protein_function_unified",
    "format_protein_report",
    "get_database_fingerprint",
    "load_local_annotation",
    "normalize_sequence",
    "query_protein",
    "scan_pfam",
    "search_swissprot",
]