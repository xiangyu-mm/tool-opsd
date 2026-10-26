"""Streaming UniProt XML -> SQLite annotation index."""

import csv
import gzip
import hashlib
import json
import logging
import os
import sqlite3
import tempfile
import xml.etree.ElementTree as ET

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List


logger = logging.getLogger(__name__)

NS_URI = "https://uniprot.org/uniprot"
NS = {"u": NS_URI}
ENTRY_TAG = f"{{{NS_URI}}}entry"


def open_binary(path: str):
    if path.endswith(".gz"):
        return gzip.open(path, "rb")
    return open(path, "rb")


def open_text(path: str):
    if path.endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8")
    return open(path, "r", encoding="utf-8")


def element_text(element) -> str:
    if element is None:
        return ""
    return " ".join("".join(element.itertext()).split())


def find_text(element, path: str) -> str:
    return element_text(element.find(path, NS))


def evidence_refs(element) -> List[str]:
    """References point to entry-level evidence definitions."""
    return element.get("evidence", "").split()


def file_signature(path: str) -> Dict[str, Any]:
    result = {
        "path": os.path.abspath(path) if path else None,
        "exists": bool(path and os.path.isfile(path)),
    }

    if result["exists"]:
        stat = os.stat(path)
        result.update({
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
        })

    return result


def parse_db_reference(element) -> Dict[str, Any]:
    return {
        "database": element.get("type"),
        "id": element.get("id"),
        "properties": [
            dict(prop.attrib)
            for prop in element.findall("u:property", NS)
        ],
        "evidence_refs": evidence_refs(element),
    }


def comment_to_text(comment) -> str:
    """
    Produce readable text for existing report code.

    Full XML and evidence references are also preserved separately.
    """
    parts = []

    for node in comment.iter():
        local_name = node.tag.rsplit("}", 1)[-1]

        if local_name in {
            "text",
            "location",
            "topology",
            "orientation",
            "name",
        }:
            text = element_text(node)
            if text and text not in parts:
                parts.append(text)

    # Some comments mainly consist of structured database references.
    for ref in comment.findall(".//u:dbReference", NS):
        value = f"{ref.get('type')}:{ref.get('id')}"
        if value not in parts:
            parts.append(value)

    return "; ".join(parts)


def parse_feature(feature) -> Dict[str, Any]:
    location = feature.find("u:location", NS)
    location_parts = []

    if location is not None:
        for position in location:
            local_name = position.tag.rsplit("}", 1)[-1]
            attributes = ", ".join(
                f"{key}={value}"
                for key, value in position.attrib.items()
            )
            location_parts.append(
                f"{local_name}({attributes})"
            )

    return {
        "type": feature.get("type"),
        "location": "; ".join(location_parts),
        "description": feature.get("description"),
        "evidence": feature.get("evidence"),
        "coordinate_system": "reference_1_based_inclusive",
        "location_xml": (
            ET.tostring(location, encoding="unicode")
            if location is not None else None
        ),
    }


def uniprot_xml_entry_to_dict(entry) -> Dict[str, Any]:
    accessions = [
        element_text(node)
        for node in entry.findall("u:accession", NS)
    ]

    if not accessions:
        raise ValueError("UniProt XML entry has no accession.")

    sequence = "".join(
        find_text(entry, "u:sequence").split()
    )

    if not sequence:
        raise ValueError(
            f"UniProt entry {accessions[0]} has no sequence."
        )

    names = []

    for path in [
        "u:protein/u:recommendedName/u:fullName",
        "u:protein/u:submittedName/u:fullName",
        "u:protein/u:alternativeName/u:fullName",
    ]:
        for node in entry.findall(path, NS):
            text = element_text(node)
            if text and text not in names:
                names.append(text)

    ec_numbers = sorted(set(
        element_text(node)
        for node in entry.findall(".//u:ecNumber", NS)
        if element_text(node)
    ))

    organism = entry.find("u:organism", NS)
    organism_name = ""
    taxonomy_ids = []

    if organism is not None:
        for name in organism.findall("u:name", NS):
            if name.get("type") == "scientific":
                organism_name = element_text(name)
                break

        taxonomy_ids = [
            ref.get("id")
            for ref in organism.findall("u:dbReference", NS)
            if ref.get("type") == "NCBI Taxonomy"
        ]

    sections = {
        "function": [],
        "cofactor": [],
        "pathway": [],
        "subcellular_location": [],
        "subunit": [],
        "similarity": [],
        "activity_regulation": [],
    }

    comment_field_map = {
        "function": "function",
        "cofactor": "cofactor",
        "pathway": "pathway",
        "subcellular location": "subcellular_location",
        "subunit": "subunit",
        "similarity": "similarity",
        "activity regulation": "activity_regulation",
    }

    reactions = []
    raw_comments = []

    for comment in entry.findall("u:comment", NS):
        comment_type = comment.get("type", "")
        readable_text = comment_to_text(comment)

        raw_comments.append({
            "type": comment_type,
            "text": readable_text,
            "evidence_refs": evidence_refs(comment),
            "xml": ET.tostring(
                comment,
                encoding="unicode",
            ),
        })

        field = comment_field_map.get(comment_type)

        if field and readable_text:
            sections[field].append(readable_text)

        if comment_type == "catalytic activity":
            for reaction in comment.findall("u:reaction", NS):
                references = [
                    parse_db_reference(ref)
                    for ref in reaction.findall("u:dbReference", NS)
                ]

                rhea_ids = []
                reaction_ecs = []

                for ref in references:
                    db = (ref["database"] or "").lower()
                    identifier = ref["id"] or ""

                    if db == "rhea":
                        value = identifier.rsplit(":", 1)[-1]
                        if value.isdigit():
                            rhea_ids.append(value)

                    elif db == "ec":
                        reaction_ecs.append(identifier)

                ec_numbers = sorted(set(
                    ec_numbers + reaction_ecs
                ))

                reactions.append({
                    "equation": (
                        find_text(reaction, "u:text") or None
                    ),
                    "rhea_ids": sorted(set(rhea_ids)),
                    "ec_numbers": reaction_ecs,
                    "evidence_refs": sorted(set(
                        evidence_refs(comment)
                        + evidence_refs(reaction)
                    )),
                    "database_references": references,
                    "raw_annotation": ET.tostring(
                        comment,
                        encoding="unicode",
                    ),
                })

    go_annotations = []
    cross_references = []

    for ref in entry.findall("u:dbReference", NS):
        parsed = parse_db_reference(ref)
        database = parsed["database"]

        if database == "GO":
            properties = {
                item.get("type"): item.get("value")
                for item in parsed["properties"]
            }

            go_annotations.append({
                "id": parsed["id"],
                "term": properties.get("term"),
                "evidence": properties.get("evidence"),
                "evidence_refs": parsed["evidence_refs"],
                "properties": parsed["properties"],
            })

        if database in {
            "PDB",
            "AlphaFoldDB",
            "Pfam",
            "PROSITE",
            "InterPro",
            "KEGG",
            "Reactome",
        }:
            cross_references.append(parsed)

    # Retain all features; report code can truncate displayed results.
    features = [
        parse_feature(feature)
        for feature in entry.findall("u:feature", NS)
    ]

    evidence_definitions = [
        {
            "key": evidence.get("key"),
            "type": evidence.get("type"),
            "xml": ET.tostring(evidence, encoding="unicode"),
        }
        for evidence in entry.findall("u:evidence", NS)
    ]

    return {
        "accession": accessions[0],
        "accessions": accessions,
        "entry_name": find_text(entry, "u:name"),
        "reviewed": entry.get("dataset") == "Swiss-Prot",
        "protein_name": names[0] if names else "",
        "alternative_names": names[1:],
        "organism": organism_name,
        "taxonomy_ids": taxonomy_ids,
        "sequence": sequence,
        "sequence_length": len(sequence),
        "sequence_sha256": hashlib.sha256(
            sequence.encode("ascii")
        ).hexdigest(),
        "ec_numbers": ec_numbers,
        **sections,
        "catalytic_activity": reactions,
        "go_annotations": go_annotations,
        "features": features,
        "cross_references": cross_references,
        "annotation_comments": raw_comments,
        "evidence_definitions": evidence_definitions,
        "source": "local_uniprot_swissprot_xml",
        "entry_created": entry.get("created"),
        "entry_modified": entry.get("modified"),
        "entry_version": entry.get("version"),
    }


def iter_uniprot_annotations(
    xml_path: str,
) -> Iterator[Dict[str, Any]]:
    """Stream UniProt entries with an early namespace check."""
    with open_binary(xml_path) as handle:
        context = ET.iterparse(
            handle,
            events=("start", "end"),
        )

        try:
            _, root = next(context)
        except StopIteration:
            raise ValueError("XML file is empty.")

        expected_root = f"{{{NS_URI}}}uniprot"

        if root.tag != expected_root:
            raise ValueError(
                "Unexpected UniProt XML root/namespace. "
                f"Actual: {root.tag!r}; "
                f"expected: {expected_root!r}. "
                "Check NS_URI in xml_index.py."
            )

        for event, element in context:
            if event != "end" or element.tag != ENTRY_TAG:
                continue

            annotation = uniprot_xml_entry_to_dict(element)

            element.clear()
            root.clear()

            yield annotation

def build_xml_annotation_index(
    *,
    xml_path: str,
    index_path: str,
    rhea_mapping_path: str = "",
) -> Dict[str, Any]:
    if not os.path.isfile(xml_path):
        raise FileNotFoundError(
            f"Swiss-Prot XML file missing: {xml_path}"
        )

    destination = Path(index_path).absolute()
    destination.parent.mkdir(parents=True, exist_ok=True)

    fd, temporary = tempfile.mkstemp(
        prefix=destination.name + ".",
        suffix=".sqlite",
        dir=str(destination.parent),
    )
    os.close(fd)

    counts = {
        "proteins": 0,
        "rhea_mapping_rows_processed": 0,
    }
    warnings = []

    try:
        with sqlite3.connect(temporary) as connection:
            connection.executescript("""
                CREATE TABLE proteins (
                    accession TEXT PRIMARY KEY,
                    sequence_sha256 TEXT NOT NULL,
                    annotation_json TEXT NOT NULL
                );

                CREATE INDEX protein_sequence_hash_idx
                    ON proteins(sequence_sha256);

                CREATE TABLE aliases (
                    alias TEXT PRIMARY KEY,
                    accession TEXT NOT NULL
                );

                CREATE TABLE rhea_links (
                    accession TEXT NOT NULL,
                    rhea_id TEXT NOT NULL,
                    master_id TEXT NOT NULL DEFAULT '',
                    direction TEXT NOT NULL DEFAULT '',
                    UNIQUE(accession, rhea_id, master_id, direction)
                );

                CREATE INDEX rhea_accession_idx
                    ON rhea_links(accession);

                CREATE TABLE metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
            """)

            for annotation in iter_uniprot_annotations(xml_path):
                primary = annotation["accession"]

                connection.execute(
                    "INSERT INTO proteins VALUES (?, ?, ?)",
                    (
                        primary,
                        annotation["sequence_sha256"],
                        json.dumps(
                            annotation,
                            ensure_ascii=False,
                        ),
                    ),
                )

                connection.executemany(
                    "INSERT OR REPLACE INTO aliases VALUES (?, ?)",
                    [
                        (alias, primary)
                        for alias in annotation["accessions"]
                    ],
                )

                counts["proteins"] += 1

                if counts["proteins"] % 10000 == 0:
                    connection.commit()
                    logger.info(
                        "Indexed %s proteins",
                        counts["proteins"],
                    )

            if counts["proteins"] == 0:
                raise ValueError(
                    "No UniProt entries parsed. "
                    "Check the XML file and namespace."
                )

            if (
                rhea_mapping_path
                and os.path.isfile(rhea_mapping_path)
            ):
                with open_text(rhea_mapping_path) as handle:
                    reader = csv.DictReader(
                        handle,
                        delimiter="\t",
                    )

                    if not reader.fieldnames:
                        raise ValueError(
                            "Rhea mapping file has no header."
                        )

                    reader.fieldnames = [
                        field.strip().lstrip("\ufeff")
                        for field in reader.fieldnames
                    ]

                    if not {"ID", "RHEA_ID"}.issubset(
                        reader.fieldnames
                    ):
                        raise ValueError(
                            "Unexpected Rhea mapping columns: "
                            f"{reader.fieldnames}. "
                            "Expected ID and RHEA_ID."
                        )

                    for row in reader:
                        accession = (row.get("ID") or "").strip()
                        rhea_id = (
                            row.get("RHEA_ID") or ""
                        ).strip()

                        if not accession or not rhea_id:
                            continue

                        connection.execute(
                            """
                            INSERT OR IGNORE INTO rhea_links
                            VALUES (?, ?, ?, ?)
                            """,
                            (
                                accession,
                                rhea_id,
                                (row.get("MASTER_ID") or "").strip(),
                                (row.get("DIRECTION") or "").strip(),
                            ),
                        )

                        counts["rhea_mapping_rows_processed"] += 1

            else:
                warnings.append(
                    "Rhea TSV mapping was not imported. "
                    "Rhea references from XML remain available."
                )

            metadata = {
                "schema_version": "3",
                "annotation_format": "uniprot_xml",
                "built_at": datetime.now(
                    timezone.utc
                ).isoformat(),
                "xml_signature": json.dumps(
                    file_signature(xml_path)
                ),
                "rhea_mapping_signature": json.dumps(
                    file_signature(rhea_mapping_path)
                ),
            }

            connection.executemany(
                "INSERT INTO metadata VALUES (?, ?)",
                list(metadata.items()),
            )
            connection.commit()

        os.replace(temporary, destination)

    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

    return {
        "index_path": str(destination),
        **counts,
        "warnings": warnings,
    }