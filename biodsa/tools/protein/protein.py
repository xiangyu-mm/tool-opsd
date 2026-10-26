"""General protein query, sequence analysis, and annotation retrieval."""

import argparse
import csv
import gzip
import hashlib
import json
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile

from collections import Counter
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


logger = logging.getLogger(__name__)

TOOL_VERSION = "1.2"


# ============================================================
# Configuration
# ============================================================

PROTEIN_KB_ROOT = os.getenv(
    "PROTEIN_KB_ROOT",
    "/home/data4/xiangyu/dataset/protein_knowledgebase",
)

SWISSPROT_DIAMOND_PATH = os.getenv(
    "SWISSPROT_DIAMOND_PATH",
    os.path.join(PROTEIN_KB_ROOT, "uniport", "uniprot_sprot.dmnd"),
)

SWISSPROT_XML_PATH = os.getenv(
    "SWISSPROT_XML_PATH",
    os.path.join(
        PROTEIN_KB_ROOT,
        "uniport",
        "uniprot_sprot.xml.gz",
    ),
)

PROTEIN_INDEX_PATH = os.getenv(
    "PROTEIN_INDEX_PATH",
    os.path.join(PROTEIN_KB_ROOT, "indexes", "protein_annotations.sqlite"),
)

RHEA_UNIPROT_PATH = os.getenv(
    "RHEA_UNIPROT_PATH",
    os.path.join(PROTEIN_KB_ROOT, "Rhea", "rhea2uniprot_sprot.tsv"),
)

PFAM_HMM_PATH = os.getenv("PFAM_HMM_PATH", "/home/data4/xiangyu/dataset/protein_knowledgebase/pfam/Pfam-A.hmm")

DIAMOND_BIN = os.getenv("DIAMOND_BIN", "diamond")
HMMSCAN_BIN = os.getenv("HMMSCAN_BIN", "hmmscan")


# These describe implemented evidence sections, not allowed questions.
SUPPORTED_ANALYSIS_TOPICS = {
    "sequence_properties",
    "homology",
    "function",
    "catalytic_activity",
    "cofactor",
    "pathway",
    "localization",
    "subunit",
    "regulation",
    "go",
    "reference_features",
    "domains",
}

DEFAULT_ANALYSIS_TOPICS = [
    "sequence_properties",
    "homology",
    "function",
    "catalytic_activity",
    "cofactor",
    "pathway",
    "localization",
    "subunit",
    "regulation",
    "go",
    "reference_features",
]

TOPIC_ALIASES = {
    "general_function": "function",
    "protein_function": "function",
    "reaction": "catalytic_activity",
    "catalysis": "catalytic_activity",
    "ec": "catalytic_activity",
    "rhea": "catalytic_activity",
    "subcellular_location": "localization",
    "activity_regulation": "regulation",
    "go_annotations": "go",
    "features": "reference_features",
    "pfam": "domains",
}

STANDARD_AMINO_ACIDS = set("ACDEFGHIKLMNPQRSTVWY")


# ============================================================
# Generic helpers
# ============================================================

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_json(data: Any, save_path: Optional[str]) -> None:
    """Atomically save JSON without modifying source databases."""
    if not save_path:
        return

    destination = Path(save_path).absolute()
    destination.parent.mkdir(parents=True, exist_ok=True)

    fd, temporary = tempfile.mkstemp(
        prefix=destination.name + ".",
        suffix=".tmp",
        dir=str(destination.parent),
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(
                data,
                handle,
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
            )
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def open_text(path: str):
    if path.endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8")
    return open(path, "r", encoding="utf-8")


def file_signature(path: str) -> Dict[str, Any]:
    result = {"path": os.path.abspath(path) if path else None}

    if path and os.path.isfile(path):
        stat = os.stat(path)
        result.update({
            "exists": True,
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
        })
    else:
        result["exists"] = False

    return result


def get_database_fingerprint() -> Dict[str, Any]:
    """Cheap provenance/cache signature, not a content checksum."""
    return {
        "tool_version": TOOL_VERSION,
        "diamond": file_signature(SWISSPROT_DIAMOND_PATH),
        "annotation_index": file_signature(PROTEIN_INDEX_PATH),
        "pfam": file_signature(PFAM_HMM_PATH),
    }


def require_executable(executable: str) -> None:
    if not shutil.which(executable):
        raise RuntimeError(
            f"Executable not found: {executable}. "
            "Install the program or configure its executable path."
        )


def normalize_sequence(sequence: str) -> str:
    """Accept a plain sequence, one FASTA entry, or one fenced sequence."""
    if not isinstance(sequence, str):
        raise ValueError("Protein sequence must be a string.")

    text = sequence.strip()

    if text.startswith("```"):
        blocks = re.findall(
            r"```[^\n]*\n(.*?)```",
            text,
            flags=re.S,
        )
        if len(blocks) != 1:
            raise ValueError("Expected one fenced sequence block.")
        text = blocks[0]

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    header_count = sum(line.startswith(">") for line in lines)
    if header_count > 1:
        raise ValueError("Only one FASTA entry is accepted per call.")

    sequence = "".join(
        line for line in lines if not line.startswith(">")
    )
    sequence = re.sub(r"\s+", "", sequence).upper()

    if sequence.endswith("*"):
        sequence = sequence[:-1]

    if not sequence:
        raise ValueError("Protein sequence is empty.")

    if not re.fullmatch(r"[ACDEFGHIKLMNPQRSTVWYBXZJUO]+", sequence):
        raise ValueError(
            "Invalid protein sequence. Supply amino-acid letters only, "
            "a single FASTA entry, or a fenced sequence block."
        )

    if len(sequence) > 100000:
        raise ValueError("Sequence exceeds the 100000-residue limit.")

    return sequence


def normalize_accession(accession: str) -> str:
    text = accession.strip().upper()

    if "|" in text:
        parts = text.split("|")
        if len(parts) >= 3:
            text = parts[1]

    pattern = (
        r"(?:[OPQ][0-9][A-Z0-9]{3}[0-9]|"
        r"[A-NR-Z][0-9](?:[A-Z][A-Z0-9]{2}[0-9]){1,2})"
    )

    if not re.fullmatch(pattern, text):
        raise ValueError(
            "Invalid UniProt primary accession. "
            "Isoform identifiers are not supported by this interface."
        )

    return text


def subject_accession(subject: str) -> str:
    parts = subject.split("|")
    return parts[1] if len(parts) >= 3 else subject


def normalize_analysis_topics(
    topics: Optional[List[str]],
) -> List[str]:
    if topics is None:
        return list(DEFAULT_ANALYSIS_TOPICS)

    if not isinstance(topics, list):
        raise ValueError("analysis_topics must be a list of strings.")

    normalized = []

    for topic in topics:
        if not isinstance(topic, str) or not topic.strip():
            raise ValueError(
                "analysis_topics must contain nonempty strings."
            )

        name = topic.strip().lower().replace("-", "_").replace(" ", "_")
        name = TOPIC_ALIASES.get(name, name)

        if name not in normalized:
            normalized.append(name)

    return normalized


def extract_rhea_ids(text: str) -> List[str]:
    return sorted(set(
        re.findall(r"RHEA:(\d+)", text, flags=re.I)
    ))


def strip_evidence(text: str) -> str:
    return re.sub(r"\s*\{[^{}]*\}", "", text).strip()


# ============================================================
# HTTP fallback
# ============================================================

def create_http_session() -> requests.Session:
    retry = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
    )

    session = requests.Session()
    session.headers["User-Agent"] = "BioDSA-Protein-Toolkit/1.2"
    session.mount(
        "https://",
        HTTPAdapter(max_retries=retry),
    )
    return session


HTTP_SESSION = create_http_session()


# ============================================================
# Sequence-derived properties
# ============================================================

def compute_sequence_properties(
    sequence: str,
) -> Dict[str, Any]:
    from Bio.SeqUtils.ProtParam import ProteinAnalysis

    counts = Counter(sequence)
    length = len(sequence)

    result = {
        "length": length,
        "amino_acid_counts": dict(sorted(counts.items())),
        "amino_acid_fractions": {
            aa: round(count / length, 6)
            for aa, count in sorted(counts.items())
        },
        "nonstandard_residues": sorted(
            set(sequence) - STANDARD_AMINO_ACIDS
        ),
        "method": "Biopython ProtParam",
        "warnings": [],
    }

    if result["nonstandard_residues"]:
        result["warnings"].append(
            "Physicochemical calculations were skipped because ambiguous "
            "or nonstandard amino-acid letters are present."
        )
        return result

    analyzer = ProteinAnalysis(sequence)

    result.update({
        "molecular_weight_da": round(
            analyzer.molecular_weight(), 3
        ),
        "theoretical_isoelectric_point": round(
            analyzer.isoelectric_point(), 3
        ),
        "aromaticity": round(analyzer.aromaticity(), 6),
        "instability_index": round(
            analyzer.instability_index(), 3
        ),
        "gravy": round(analyzer.gravy(), 4),
        "charge_at_ph7": round(
            analyzer.charge_at_pH(7.0), 4
        ),
    })

    result["warnings"].append(
        "Sequence-derived estimates assume an unmodified protein and do "
        "not account for processing, PTMs, bound ligands, or oligomers."
    )
    return result


# ============================================================
# UniProt DAT parsing
# ============================================================

def swissprot_record_to_dict(record) -> Dict[str, Any]:
    """
    Preserve source annotation text and evidence codes.

    sequence is stored internally to support accession-based sequence
    analysis. It is omitted from compact annotation reports.
    """
    sections: Dict[str, List[str]] = {}

    for comment in record.comments:
        if ": " in comment:
            category, text = comment.split(": ", 1)
        else:
            category, text = "OTHER", comment

        sections.setdefault(category, []).append(text)

    catalytic_comments = sections.get("CATALYTIC ACTIVITY", [])
    reactions = []

    for text in catalytic_comments:
        match = re.search(
            r"(?:^|\s)Reaction=(.*?)(?=;\s*(?:Xref|EC|Evidence)=|$)",
            text,
        )

        reactions.append({
            "equation": (
                strip_evidence(match.group(1)).rstrip(";")
                if match else None
            ),
            "rhea_ids": extract_rhea_ids(text),
            "raw_annotation": text,
        })

    go_annotations = []
    cross_references = []

    for ref in record.cross_references:
        if not ref:
            continue

        if ref[0] == "GO":
            go_annotations.append({
                "id": ref[1],
                "term": ref[2] if len(ref) > 2 else None,
                "evidence": ref[3] if len(ref) > 3 else None,
            })

        if ref[0] in {
            "PDB", "AlphaFoldDB", "Pfam", "PROSITE",
            "InterPro", "KEGG", "Reactome",
        }:
            cross_references.append({
                "database": ref[0],
                "fields": list(ref[1:]),
            })

    features = []

    for feature in record.features:
        if feature.type not in {
            "ACT_SITE", "BINDING", "DOMAIN", "REGION",
            "MOTIF", "SITE", "METAL",
        }:
            continue

        qualifiers = getattr(feature, "qualifiers", {})

        features.append({
            "type": feature.type,
            "location": str(feature.location),
            "description": (
                qualifiers.get("description")
                or qualifiers.get("note")
            ),
            "evidence": qualifiers.get("evidence"),
            "coordinate_system": "reference_protein",
        })

    ec_numbers = sorted(set(
        re.findall(
            r"\bEC[=:\s]+([0-9-]+\.[0-9-]+\.[0-9-]+\.[0-9-]+)",
            record.description + " " + " ".join(catalytic_comments),
        )
    ))

    sequence = record.sequence

    return {
        "accession": record.accessions[0],
        "accessions": list(record.accessions),
        "entry_name": record.entry_name,
        "reviewed": record.data_class == "Reviewed",
        "protein_name": record.description,
        "organism": record.organism,
        "taxonomy_ids": list(record.taxonomy_id),
        "sequence_length": len(sequence),
        "sequence": sequence,
        "sequence_sha256": hashlib.sha256(
            sequence.encode("ascii")
        ).hexdigest(),
        "ec_numbers": ec_numbers,
        "function": sections.get("FUNCTION", []),
        "catalytic_activity": reactions,
        "cofactor": sections.get("COFACTOR", []),
        "pathway": sections.get("PATHWAY", []),
        "subcellular_location": sections.get(
            "SUBCELLULAR LOCATION", []
        ),
        "subunit": sections.get("SUBUNIT", []),
        "similarity": sections.get("SIMILARITY", []),
        "activity_regulation": sections.get(
            "ACTIVITY REGULATION", []
        ),
        "go_annotations": go_annotations,
        "features": features,
        "cross_references": cross_references,
        "source": "local_uniprot_swissprot_dat",
    }


# ============================================================
# One-time SQLite annotation index
# ============================================================

def build_protein_annotation_index(
    xml_path: str = SWISSPROT_XML_PATH,
    index_path: str = PROTEIN_INDEX_PATH,
    rhea_mapping_path: str = RHEA_UNIPROT_PATH,
) -> Dict[str, Any]:
    from biodsa.tools.protein.xml_index import (
        build_xml_annotation_index,
    )

    return build_xml_annotation_index(
        xml_path=xml_path,
        index_path=index_path,
        rhea_mapping_path=rhea_mapping_path,
    )


def load_local_annotation(
    accession: str,
    index_path: str = PROTEIN_INDEX_PATH,
) -> Optional[Dict[str, Any]]:
    if not os.path.isfile(index_path):
        return None

    uri = Path(index_path).absolute().as_uri() + "?mode=ro"

    with sqlite3.connect(uri, uri=True) as connection:
        row = connection.execute(
            """
            SELECT p.annotation_json
            FROM aliases a
            JOIN proteins p ON p.accession = a.accession
            WHERE a.alias = ?
            """,
            (accession,),
        ).fetchone()

        if not row:
            return None

        data = json.loads(row[0])
        aliases = data.get("accessions", [data["accession"]])
        placeholders = ",".join("?" for _ in aliases)

        links = connection.execute(
            f"""
            SELECT DISTINCT rhea_id, master_id, direction
            FROM rhea_links
            WHERE accession IN ({placeholders})
            """,
            aliases,
        ).fetchall()

        data["rhea_links"] = [
            {
                "rhea_id": item[0],
                "master_id": item[1] or None,
                "direction": item[2] or None,
            }
            for item in links
        ]

        return data


# ============================================================
# Online UniProt fallback
# ============================================================

def fetch_online_annotation(
    accession: str,
) -> Optional[Dict[str, Any]]:
    from Bio import SwissProt

    accession = normalize_accession(accession)
    url = (
        f"https://rest.uniprot.org/uniprotkb/{accession}.txt"
    )

    try:
        response = HTTP_SESSION.get(
            url,
            timeout=(10, 40),
        )

        if response.status_code == 404:
            return None

        response.raise_for_status()

        record = SwissProt.read(StringIO(response.text))
        data = swissprot_record_to_dict(record)

        data["source"] = "uniprot_rest"
        data["source_url"] = url
        data["retrieved_at"] = utc_now()
        data["rhea_links"] = []

        return data

    except (
        requests.RequestException,
        ValueError,
        StopIteration,
    ) as exc:
        logger.warning(
            "UniProt lookup failed for %s: %s",
            accession,
            exc,
        )
        return None


def get_annotation(
    accession: str,
    allow_online: bool,
) -> Optional[Dict[str, Any]]:
    data = load_local_annotation(accession)

    if data:
        return data

    if allow_online:
        return fetch_online_annotation(accession)

    return None


# ============================================================
# DIAMOND homology search
# ============================================================

def search_swissprot(
    sequence: str,
    workdir: str,
    max_hits: int = 20,
    threads: int = 8,
    timeout: int = 600,
) -> List[Dict[str, Any]]:
    require_executable(DIAMOND_BIN)

    if not os.path.isfile(SWISSPROT_DIAMOND_PATH):
        raise FileNotFoundError(
            "DIAMOND database missing: "
            + SWISSPROT_DIAMOND_PATH
        )

    os.makedirs(workdir, exist_ok=True)

    query_path = os.path.join(workdir, "query.fasta")
    output_path = os.path.join(workdir, "diamond_hits.tsv")

    with open(query_path, "w", encoding="utf-8") as handle:
        handle.write(">query\n" + sequence + "\n")

    command = [
        DIAMOND_BIN,
        "blastp",
        "--query", query_path,
        "--db", SWISSPROT_DIAMOND_PATH,
        "--out", output_path,
        "--outfmt", "6",
        "qseqid", "sseqid", "pident", "length",
        "qlen", "slen",
        "qstart", "qend", "sstart", "send",
        "evalue", "bitscore",
        "--max-target-seqs", str(max_hits),
        "--max-hsps", "1",
        "--evalue", "1e-5",
        "--very-sensitive",
        "--threads", str(threads),
    ]

    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )

    if completed.returncode != 0:
        raise RuntimeError(
            f"DIAMOND failed:\n{completed.stderr[-4000:]}"
        )

    hits = []

    with open(output_path, encoding="utf-8") as handle:
        for line in handle:
            fields = line.rstrip("\n").split("\t")

            if len(fields) != 12:
                continue

            qlen = int(fields[4])
            slen = int(fields[5])
            qstart = int(fields[6])
            qend = int(fields[7])
            sstart = int(fields[8])
            send = int(fields[9])

            query_coverage = (qend - qstart + 1) / qlen
            target_coverage = (send - sstart + 1) / slen

            hits.append({
                "accession": subject_accession(fields[1]),
                "subject_id": fields[1],
                "identity_percent": float(fields[2]),
                "alignment_length": int(fields[3]),
                "query_length": qlen,
                "target_length": slen,
                "query_start": qstart,
                "query_end": qend,
                "target_start": sstart,
                "target_end": send,
                "query_coverage": round(query_coverage, 6),
                "target_coverage": round(target_coverage, 6),
                "coverage_definition": "single_alignment_span_fraction",
                "evalue": float(fields[10]),
                "bitscore": float(fields[11]),
            })

    hits.sort(
        key=lambda item: item["bitscore"],
        reverse=True,
    )
    return hits


# ============================================================
# Optional Pfam verification
# ============================================================

def scan_pfam(
    sequence: str,
    workdir: str,
    threads: int = 8,
    timeout: int = 600,
) -> List[Dict[str, Any]]:
    require_executable(HMMSCAN_BIN)

    if not PFAM_HMM_PATH or not os.path.isfile(PFAM_HMM_PATH):
        raise FileNotFoundError(
            "PFAM_HMM_PATH is not configured or does not exist."
        )

    missing = [
        PFAM_HMM_PATH + suffix
        for suffix in (".h3f", ".h3i", ".h3m", ".h3p")
        if not os.path.isfile(PFAM_HMM_PATH + suffix)
    ]

    if missing:
        raise RuntimeError(
            "Pfam HMM is not pressed. Run: "
            f"hmmpress {PFAM_HMM_PATH}"
        )

    os.makedirs(workdir, exist_ok=True)

    query_path = os.path.join(workdir, "pfam_query.fasta")
    table_path = os.path.join(workdir, "pfam_domains.tsv")

    with open(query_path, "w", encoding="utf-8") as handle:
        handle.write(">query\n" + sequence + "\n")

    command = [
        HMMSCAN_BIN,
        "--cpu", str(threads),
        "--cut_ga",
        "--noali",
        "--domtblout", table_path,
        PFAM_HMM_PATH,
        query_path,
    ]

    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )

    if completed.returncode != 0:
        raise RuntimeError(
            f"hmmscan failed:\n{completed.stderr[-4000:]}"
        )

    domains = []

    with open(table_path, encoding="utf-8") as handle:
        for line in handle:
            if not line.strip() or line.startswith("#"):
                continue

            # HMMER domtblout: 22 fixed fields + optional description.
            fields = line.strip().split(maxsplit=22)

            if len(fields) < 22:
                continue

            domains.append({
                "domain_name": fields[0],
                "pfam_accession": fields[1],
                "model_length": int(fields[2]),
                "query_name": fields[3],
                "query_length": int(fields[5]),
                "full_sequence_evalue": float(fields[6]),
                "full_sequence_score": float(fields[7]),
                "domain_index": int(fields[9]),
                "domain_count": int(fields[10]),
                "conditional_evalue": float(fields[11]),
                "independent_evalue": float(fields[12]),
                "domain_score": float(fields[13]),
                "hmm_start": int(fields[15]),
                "hmm_end": int(fields[16]),
                "alignment_start": int(fields[17]),
                "alignment_end": int(fields[18]),
                "envelope_start": int(fields[19]),
                "envelope_end": int(fields[20]),
                "accuracy": float(fields[21]),
                "description": fields[22] if len(fields) > 22 else "",
                "coordinate_system": "query_1_based_inclusive",
                "method": "hmmscan --cut_ga",
            })

    domains.sort(
        key=lambda item: (
            item["alignment_start"],
            item["independent_evalue"],
        )
    )
    return domains


# ============================================================
# Evidence preparation
# ============================================================

def compact_annotation(
    annotation: Dict[str, Any],
) -> Dict[str, Any]:
    """Exclude the full reference sequence from agent-facing annotations."""
    keys = [
        "accession",
        "accessions",
        "entry_name",
        "reviewed",
        "protein_name",
        "alternative_names",
        "organism",
        "taxonomy_ids",
        "sequence_length",
        "sequence_sha256",
        "ec_numbers",
        "function",
        "catalytic_activity",
        "cofactor",
        "pathway",
        "subcellular_location",
        "subunit",
        "similarity",
        "activity_regulation",
        "go_annotations",
        "features",
        "cross_references",
        "rhea_links",
        "annotation_comments",
        "evidence_definitions",
        "entry_created",
        "entry_modified",
        "entry_version",
        "source",
        "source_url",
        "retrieved_at",
    ]

    return {
        key: annotation[key]
        for key in keys
        if key in annotation
    }


def summarize_reaction_candidates(
    evidence: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Group identical annotated equations.

    Do not merge reactions merely because they share an EC number.
    Rhea direction/master IDs are retained, not silently interchanged.
    """
    groups: Dict[str, Dict[str, Any]] = {}

    for item in evidence:
        annotation = item["annotation"]
        accession = annotation["accession"]

        for activity in annotation.get("catalytic_activity", []):
            equation = activity.get("equation")
            rhea_ids = activity.get("rhea_ids", [])

            if equation:
                normalized_equation = re.sub(
                    r"\s+", " ", equation
                ).strip()
                key = "equation:" + normalized_equation
            elif rhea_ids:
                key = "rhea:" + ",".join(sorted(rhea_ids))
            else:
                continue

            if key not in groups:
                groups[key] = {
                    "equation": equation,
                    "rhea_ids": [],
                    "supporting_accessions": [],
                    "support_count": 0,
                    "best_alignment": None,
                    "interpretation": (
                        "Annotated reaction of reference proteins. "
                        "Transfer to a homologous query requires assessment."
                    ),
                }

            group = groups[key]

            group["rhea_ids"] = sorted(set(
                group["rhea_ids"] + rhea_ids
            ))

            if accession not in group["supporting_accessions"]:
                group["supporting_accessions"].append(accession)
                group["support_count"] += 1

            alignment = item.get("alignment")
            previous = group["best_alignment"]

            if alignment and (
                previous is None
                or alignment["bitscore"] > previous["bitscore"]
            ):
                group["best_alignment"] = alignment

    candidates = list(groups.values())

    candidates.sort(
        key=lambda item: (
            -(
                item["best_alignment"]["bitscore"]
                if item["best_alignment"] else 0
            ),
            -item["support_count"],
        )
    )
    return candidates


def assess_functional_evidence(
    evidence: List[Dict[str, Any]],
    query_mode: str,
    reaction_candidates: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Heuristic annotation evidence grade, not a calibrated probability."""
    if not evidence:
        return {
            "level": "insufficient",
            "basis": "No reference annotation was retrieved.",
            "calibrated_probability": False,
            "multiple_reaction_candidates": False,
        }

    if query_mode == "accession":
        level = "direct_annotation_lookup"
        basis = (
            "Annotations refer to the requested accession. "
            "Inspect original evidence codes."
        )

    elif any(
        item.get("exact_sequence_match")
        for item in evidence
    ):
        level = "exact_sequence_annotation"
        basis = (
            "Query and reference sequence hashes match. "
            "Source annotations may still be inferred rather than experimental."
        )

    else:
        alignments = [
            item["alignment"]
            for item in evidence
            if item.get("alignment")
        ]

        if not alignments:
            return {
                "level": "ungraded",
                "basis": "No sequence alignment is available for grading.",
                "calibrated_probability": False,
                "multiple_reaction_candidates": (
                    len(reaction_candidates) > 1
                ),
            }

        best = max(
            alignments,
            key=lambda item: item["bitscore"],
        )

        coverage = min(
            best["query_coverage"],
            best["target_coverage"],
        )
        identity = best["identity_percent"]

        if identity >= 70 and coverage >= 0.90:
            level = "strong_homology_support"
        elif identity >= 40 and coverage >= 0.80:
            level = "moderate_homology_support"
        else:
            level = "limited_homology_support"

        basis = (
            "Heuristic grade from identity and bidirectional alignment-span "
            "coverage; this does not establish exact substrate specificity."
        )

    return {
        "level": level,
        "basis": basis,
        "calibrated_probability": False,
        "multiple_reaction_candidates": (
            len(reaction_candidates) > 1
        ),
    }


# ============================================================
# Agent-facing report
# ============================================================

def format_protein_report(
    details: Dict[str, Any],
) -> str:
    topics = set(details.get("analysis_topics", []))

    lines = [
        "# Protein query and analysis",
        f"- Status: {details['status']}",
        f"- Query mode: {details['query']['mode']}",
        (
            "- Functional annotation evidence grade: "
            + details["confidence"]["level"]
        ),
    ]

    if details.get("user_query"):
        lines.append(
            "- User question: " + details["user_query"]
        )

    if details["query"].get("accession"):
        lines.append(
            "- Accession: " + details["query"]["accession"]
        )

    if details["query"].get("sequence_length"):
        lines.append(
            "- Sequence length: "
            + str(details["query"]["sequence_length"])
        )

    if details.get("save_path"):
        lines.append(
            "- Full evidence JSON: " + details["save_path"]
        )

    properties = details.get("sequence_properties", {})

    if properties and "sequence_properties" in topics:
        lines.append("\n## Sequence-derived properties")

        for key in [
            "length",
            "molecular_weight_da",
            "theoretical_isoelectric_point",
            "aromaticity",
            "instability_index",
            "gravy",
            "charge_at_ph7",
        ]:
            if key in properties:
                lines.append(
                    f"- {key}: {properties[key]}"
                )

        if properties.get("nonstandard_residues"):
            lines.append(
                "- Nonstandard/ambiguous letters: "
                + ", ".join(
                    properties["nonstandard_residues"]
                )
            )

        for warning in properties.get("warnings", []):
            lines.append("- Caveat: " + warning)

    field_topics = {
        "function": "function",
        "cofactor": "cofactor",
        "pathway": "pathway",
        "localization": "subcellular_location",
        "subunit": "subunit",
        "regulation": "activity_regulation",
    }

    evidence = details.get("evidence", [])

    if evidence:
        lines.append("\n## Reference-protein evidence")

        for item in evidence[:3]:
            annotation = item["annotation"]

            lines.append(
                f"\n### {annotation['accession']} — "
                f"{annotation.get('protein_name', '')}"
            )
            lines.append(
                f"- Organism: {annotation.get('organism', 'unknown')}"
            )
            lines.append(
                f"- Reviewed: {annotation.get('reviewed', False)}"
            )
            lines.append(
                f"- Source: {annotation.get('source', 'unknown')}"
            )

            alignment = item.get("alignment")

            if alignment:
                lines.append(
                    "- Homology: "
                    f"identity={alignment['identity_percent']:.1f}%, "
                    f"query coverage={alignment['query_coverage']:.1%}, "
                    f"target coverage={alignment['target_coverage']:.1%}, "
                    f"E-value={alignment['evalue']:.3g}"
                )

            if item.get("exact_sequence_match"):
                lines.append(
                    "- Exact reference sequence hash match: yes"
                )

            for topic, field in field_topics.items():
                if topic not in topics:
                    continue

                for text in annotation.get(field, [])[:3]:
                    lines.append(
                        f"- {topic}: {text}"
                    )

            if "catalytic_activity" in topics:
                ec_numbers = annotation.get("ec_numbers", [])

                if ec_numbers:
                    lines.append(
                        "- EC: " + ", ".join(ec_numbers)
                    )

                for link in annotation.get("rhea_links", [])[:8]:
                    lines.append(
                        "- Rhea mapping: "
                        f"RHEA:{link['rhea_id']}, "
                        f"master={link.get('master_id')}, "
                        f"direction={link.get('direction')}"
                    )

            if "go" in topics:
                for go in annotation.get("go_annotations", [])[:15]:
                    lines.append(
                        f"- GO: {go['id']} | "
                        f"{go.get('term') or ''} | "
                        f"evidence={go.get('evidence') or 'unknown'}"
                    )

            if "reference_features" in topics:
                for feature in annotation.get("features", [])[:15]:
                    lines.append(
                        "- Reference feature: "
                        f"{feature['type']} "
                        f"{feature['location']} "
                        f"{feature.get('description') or ''}; "
                        f"evidence={feature.get('evidence') or 'unspecified'}"
                    )

    elif "homology" in topics:
        lines.append("\n## Sequence-search hits")

        for hit in details.get("search_hits", [])[:5]:
            lines.append(
                f"- {hit['accession']}: "
                f"identity={hit['identity_percent']:.1f}%, "
                f"query coverage={hit['query_coverage']:.1%}, "
                f"target coverage={hit['target_coverage']:.1%}"
            )

    if "catalytic_activity" in topics:
        lines.append("\n## Candidate catalytic reactions")

        reactions = details.get("reaction_candidates", [])

        if not reactions:
            lines.append(
                "No explicit reaction equation was retrieved. "
                "This does not prove that the protein is nonenzymatic."
            )

        for reaction in reactions[:5]:
            lines.append(
                "- " + (
                    reaction["equation"]
                    or "Equation unavailable; inspect the Rhea reference."
                )
            )

            if reaction["rhea_ids"]:
                lines.append(
                    "  Rhea: "
                    + ", ".join(
                        "RHEA:" + value
                        for value in reaction["rhea_ids"]
                    )
                )

            lines.append(
                "  Reference accessions: "
                + ", ".join(
                    reaction["supporting_accessions"]
                )
            )

    if "domains" in topics:
        lines.append("\n## Query-sequence Pfam domains")

        domains = details.get("pfam_domains", [])

        if not domains:
            lines.append(
                "No domain results available. Inspect module status and "
                "warnings; unavailable results are not proof of absent domains."
            )

        for domain in domains[:20]:
            lines.append(
                f"- {domain['domain_name']} "
                f"({domain['pfam_accession']}), "
                f"positions {domain['alignment_start']}"
                f"–{domain['alignment_end']}, "
                f"i-Evalue={domain['independent_evalue']:.3g}"
            )

    lines.append("\n## Module status")

    for module, status in details.get("module_status", {}).items():
        lines.append(f"- {module}: {status}")

    lines.append("\n## Limitations")

    for warning in details.get("warnings", []):
        lines.append("- " + warning)

    lines.append(
        "- The text report is truncated for readability. "
        "The full JSON contains all retrieved evidence."
    )

    return "\n".join(lines)


# ============================================================
# Unified public entry point
# ============================================================

def fetch_protein_function_unified(
    *,
    sequence: Optional[str] = None,
    accession: Optional[str] = None,
    query: Optional[str] = None,
    analysis_topics: Optional[List[str]] = None,
    task_type: Optional[str] = None,
    save_path: Optional[str] = None,
    allow_online: bool = True,
    include_pfam: bool = False,
    max_hits: int = 20,
    max_annotations: int = 8,
    min_identity: float = 30.0,
    min_coverage: float = 0.70,
    threads: int = 8,
    timeout: int = 600,
) -> Tuple[Dict[str, Any], str]:
    """
    General protein query and evidence retrieval.

    Exactly one of sequence/accession is required.

    query is free-form text for agent interpretation. This backend does
    not use an LLM to infer which programs to run; analysis_topics controls
    requested analysis modules and report sections.

    task_type is retained only for compatibility with previous callers.
    No task whitelist is enforced.
    """
    if bool(sequence) == bool(accession):
        raise ValueError(
            "Provide exactly one of sequence or accession."
        )

    if query is not None and not isinstance(query, str):
        raise ValueError("query must be a string.")

    if not 1 <= max_hits <= 200:
        raise ValueError("max_hits must be between 1 and 200.")

    if not 1 <= max_annotations <= 50:
        raise ValueError(
            "max_annotations must be between 1 and 50."
        )

    if not 0 <= min_identity <= 100:
        raise ValueError(
            "min_identity must be between 0 and 100."
        )

    if not 0 <= min_coverage <= 1:
        raise ValueError(
            "min_coverage must be between 0 and 1."
        )

    if threads < 1 or timeout < 1:
        raise ValueError(
            "threads and timeout must be positive."
        )

    topics = normalize_analysis_topics(analysis_topics)

    if include_pfam and "domains" not in topics:
        topics.append("domains")

    run_pfam = "domains" in topics

    # Sequence-only physical analysis need not depend on DIAMOND.
    annotation_topics = {
        "function", "catalytic_activity", "cofactor",
        "pathway", "localization", "subunit",
        "regulation", "go", "reference_features",
    }
    run_homology = (
        "homology" in topics
        or bool(set(topics) & annotation_topics)
    )

    normalized_sequence = (
        normalize_sequence(sequence)
        if sequence else None
    )

    normalized_accession = (
        normalize_accession(accession)
        if accession else None
    )

    query_mode = (
        "sequence" if normalized_sequence else "accession"
    )

    query_hash = (
        hashlib.sha256(
            normalized_sequence.encode("ascii")
        ).hexdigest()
        if normalized_sequence else None
    )

    unsupported = [
        topic
        for topic in topics
        if topic not in SUPPORTED_ANALYSIS_TOPICS
    ]

    details: Dict[str, Any] = {
        "tool_version": TOOL_VERSION,
        "created_at": utc_now(),
        "user_query": query or "",
        "task_type": task_type,
        "analysis_topics": topics,
        "capabilities": {
            "supported_topics": sorted(
                SUPPORTED_ANALYSIS_TOPICS
            ),
            "unsupported_requested_topics": unsupported,
        },
        "query": {
            "mode": query_mode,
            "accession": normalized_accession,
            "sequence_length": (
                len(normalized_sequence)
                if normalized_sequence else None
            ),
            "sequence_sha256": query_hash,
            "sequence_source": (
                "user_input"
                if normalized_sequence else None
            ),
        },
        "configuration": {
            "allow_online": allow_online,
            "max_hits": max_hits,
            "max_annotations": max_annotations,
            "min_identity": min_identity,
            "min_coverage": min_coverage,
            "threads": threads,
            "timeout_per_external_program_seconds": timeout,
        },
        "database_fingerprint": get_database_fingerprint(),
        "status": "initializing",
        "functional_evidence_status": "not_requested",
        "module_status": {
            "sequence_properties": "not_requested",
            "homology": "not_requested",
            "annotation": "not_requested",
            "pfam": "not_requested",
        },
        "sequence_properties": {},
        "search_hits": [],
        "evidence": [],
        "reaction_candidates": [],
        "warnings": [],
        "errors": [],
        "pfam_domains": [],
        "save_path": (
            os.path.abspath(save_path)
            if save_path else None
        ),
    }

    if unsupported:
        details["warnings"].append(
            "Requested topics not implemented: "
            + ", ".join(unsupported)
            + ". Available requested analyses are still attempted."
        )

    evidence = []

    def record_error(module: str, exc: Exception) -> None:
        message = f"{type(exc).__name__}: {exc}"
        details["module_status"][module] = "error"
        details["errors"].append({
            "module": module,
            "message": message,
        })
        details["warnings"].append(
            f"{module} failed: {message}"
        )
        logger.warning("%s failed: %s", module, message)

    with tempfile.TemporaryDirectory(
        prefix="biodsa_protein_"
    ) as workdir:

        # ----------------------------------------------------
        # Accession lookup
        # ----------------------------------------------------
        if normalized_accession:
            try:
                annotation = get_annotation(
                    normalized_accession,
                    allow_online=allow_online,
                )

                if annotation:
                    details["module_status"]["annotation"] = "ok"

                    evidence.append({
                        "alignment": None,
                        "exact_sequence_match": None,
                        "relationship": "requested_accession",
                        "annotation": compact_annotation(annotation),
                    })

                    # Supports physical analysis/Pfam for accession queries
                    # when the annotation index contains the sequence.
                    reference_sequence = annotation.get("sequence")

                    if reference_sequence:
                        normalized_sequence = normalize_sequence(
                            reference_sequence
                        )
                        details["query"].update({
                            "sequence_length": len(normalized_sequence),
                            "sequence_sha256": hashlib.sha256(
                                normalized_sequence.encode("ascii")
                            ).hexdigest(),
                            "sequence_source": annotation.get("source"),
                        })

                else:
                    details["module_status"]["annotation"] = "no_result"
                    details["warnings"].append(
                        "No annotation retrieved for the requested accession."
                    )

            except Exception as exc:
                record_error("annotation", exc)

        # ----------------------------------------------------
        # Sequence homology lookup
        # ----------------------------------------------------
        elif run_homology:
            try:
                hits = search_swissprot(
                    sequence=normalized_sequence,
                    workdir=workdir,
                    max_hits=max_hits,
                    threads=threads,
                    timeout=timeout,
                )
                details["search_hits"] = hits
                details["module_status"]["homology"] = (
                    "ok" if hits else "no_result"
                )

                candidates = [
                    hit
                    for hit in hits
                    if hit["identity_percent"] >= min_identity
                    and hit["query_coverage"] >= min_coverage
                    and hit["target_coverage"] >= min_coverage
                ]

                if hits and not candidates:
                    details["warnings"].append(
                        "Hits were found, but none passed the annotation "
                        "transfer filters. Raw hits remain in search_hits."
                    )

                if candidates:
                    details["module_status"]["annotation"] = "no_result"

                seen = set()
                lookup_error_count = 0

                for hit in candidates[:max_annotations]:
                    try:
                        annotation = get_annotation(
                            hit["accession"],
                            allow_online=allow_online,
                        )
                    except Exception as exc:
                        lookup_error_count += 1
                        details["errors"].append({
                            "module": "annotation",
                            "accession": hit["accession"],
                            "message": f"{type(exc).__name__}: {exc}",
                        })
                        continue

                    if not annotation:
                        details["warnings"].append(
                            "No annotation retrieved for "
                            + hit["accession"]
                        )
                        continue

                    primary = annotation["accession"]

                    if primary in seen:
                        continue
                    seen.add(primary)

                    evidence.append({
                        "alignment": hit,
                        "exact_sequence_match": (
                            annotation.get("sequence_sha256")
                            == query_hash
                        ),
                        "relationship": "sequence_search_reference",
                        "annotation": compact_annotation(annotation),
                    })

                if evidence:
                    details["module_status"]["annotation"] = (
                        "partial" if lookup_error_count else "ok"
                    )
                elif lookup_error_count:
                    details["module_status"]["annotation"] = "error"

            except Exception as exc:
                record_error("homology", exc)

        # ----------------------------------------------------
        # Sequence physical properties
        # ----------------------------------------------------
        if "sequence_properties" in topics:
            if normalized_sequence:
                try:
                    details["sequence_properties"] = (
                        compute_sequence_properties(
                            normalized_sequence
                        )
                    )
                    details["module_status"]["sequence_properties"] = "ok"
                except Exception as exc:
                    record_error("sequence_properties", exc)
            else:
                details["module_status"]["sequence_properties"] = (
                    "unavailable"
                )
                details["warnings"].append(
                    "Sequence properties require an available sequence."
                )

        # ----------------------------------------------------
        # Pfam analysis
        # ----------------------------------------------------
        if run_pfam:
            if normalized_sequence:
                try:
                    details["pfam_domains"] = scan_pfam(
                        sequence=normalized_sequence,
                        workdir=workdir,
                        threads=threads,
                        timeout=timeout,
                    )
                    details["module_status"]["pfam"] = (
                        "ok"
                        if details["pfam_domains"]
                        else "no_result"
                    )
                except Exception as exc:
                    record_error("pfam", exc)
            else:
                details["module_status"]["pfam"] = "unavailable"
                details["warnings"].append(
                    "Pfam scanning requires an available sequence."
                )

    details["evidence"] = evidence
    details["reaction_candidates"] = (
        summarize_reaction_candidates(evidence)
    )

    details["confidence"] = assess_functional_evidence(
        evidence=evidence,
        query_mode=query_mode,
        reaction_candidates=details["reaction_candidates"],
    )

    if evidence:
        details["functional_evidence_status"] = "available"
    elif (
        normalized_accession
        or run_homology
    ):
        details["functional_evidence_status"] = "insufficient_evidence"

    successful_modules = [
        name
        for name, status in details["module_status"].items()
        if status in {"ok", "partial", "no_result"}
    ]

    failed_or_unavailable = any(
        status in {"error", "unavailable", "partial"}
        for status in details["module_status"].values()
    )

    if successful_modules:
        details["status"] = (
            "partial"
            if failed_or_unavailable or unsupported
            else "ok"
        )
    elif details["errors"]:
        details["status"] = "error"
    else:
        details["status"] = "insufficient_evidence"

    if len(details["reaction_candidates"]) > 1:
        details["warnings"].append(
            "Multiple reaction candidates were retrieved. Counts are not "
            "independent experimental support; do not choose exact substrates "
            "solely by majority vote."
        )

    # Remove duplicate warnings while retaining order.
    details["warnings"] = list(dict.fromkeys(details["warnings"]))

    save_json(details, save_path)
    return details, format_protein_report(details)


# More general alias for new callers.
query_protein = fetch_protein_function_unified


# ============================================================
# CLI
# ============================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Protein query, analysis, and XML annotation indexing."
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    build_parser = subparsers.add_parser("build-index")
    build_parser.add_argument(
        "--xml",
        default=SWISSPROT_XML_PATH,
    )
    build_parser.add_argument(
        "--index",
        default=PROTEIN_INDEX_PATH,
    )
    build_parser.add_argument(
        "--rhea-map",
        default=RHEA_UNIPROT_PATH,
    )

    query_parser = subparsers.add_parser("query")

    query_group = query_parser.add_mutually_exclusive_group(
        required=True
    )
    query_group.add_argument("--sequence")
    query_group.add_argument("--fasta")
    query_group.add_argument("--accession")

    query_parser.add_argument("--query")
    query_parser.add_argument("--topics", nargs="+", default=None)
    query_parser.add_argument("--task-type", default=None)
    query_parser.add_argument("--save")
    query_parser.add_argument("--offline", action="store_true")
    query_parser.add_argument("--pfam", action="store_true")
    query_parser.add_argument("--threads", type=int, default=8)
    query_parser.add_argument("--max-hits", type=int, default=20)
    query_parser.add_argument("--max-annotations", type=int, default=8)
    query_parser.add_argument("--min-identity", type=float, default=30.0)
    query_parser.add_argument("--min-coverage", type=float, default=0.70)
    query_parser.add_argument("--timeout", type=int, default=600)

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.command == "build-index":
        result = build_protein_annotation_index(
            xml_path=args.xml,
            index_path=args.index,
            rhea_mapping_path=args.rhea_map,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    sequence = args.sequence

    if args.fasta:
        with open(args.fasta, encoding="utf-8") as handle:
            sequence = handle.read()

    details, report = query_protein(
        sequence=sequence,
        accession=args.accession,
        query=args.query,
        analysis_topics=args.topics,
        task_type=args.task_type,
        save_path=args.save,
        allow_online=not args.offline,
        include_pfam=args.pfam,
        max_hits=args.max_hits,
        max_annotations=args.max_annotations,
        min_identity=args.min_identity,
        min_coverage=args.min_coverage,
        threads=args.threads,
        timeout=args.timeout,
    )

    print(report)

    if details["status"] == "error":
        raise SystemExit(1)


if __name__ == "__main__":
    main()