import hashlib
import json
import logging
import math
import os
import re
import sqlite3
import threading
import time
from collections import Counter
from contextlib import closing, contextmanager
from functools import lru_cache
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import quote

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

RDKIT_AVAILABLE = False
SELFIES_AVAILABLE = False

try:
    from rdkit import Chem, rdBase
    from rdkit.Chem import (
        AllChem, Descriptors, Fragments, QED, inchi, rdMolDescriptors
    )
    from rdkit.Chem.MolStandardize import rdMolStandardize

    RDKIT_AVAILABLE = True
except ImportError:
    logger.warning("RDKit is not installed.")

try:
    import selfies as sf

    SELFIES_AVAILABLE = True
except ImportError:
    logger.warning("SELFIES is not installed.")


# =====================================================================
# Database paths
# =====================================================================

LOTUS_CSV_PATH = os.getenv(
    "LOTUS_CSV_PATH",
    "/home/data4/xiangyu/dataset/chemistry_knowledgebase/"
    "LOTUS/230106_frozen_metadata.csv",
)

QM9_CSV_PATH = os.getenv(
    "QM9_CSV_PATH",
    "/home/data4/xiangyu/dataset/chemistry_knowledgebase/qm9.csv",
)

ORD_DB_PATH = os.getenv(
    "ORD_DB_PATH",
    "/home/data4/xiangyu/dataset/chemistry_knowledgebase/"
    "ORD/ord-data/ord_nlp_lite.db",
)

# 独立索引文件；不修改原 ORD 数据库。
ORD_PRODUCT_INDEX_PATH = os.getenv(
    "ORD_PRODUCT_INDEX_PATH",
    ORD_DB_PATH + ".products.idx.sqlite",
)


# =====================================================================
# HTTP
# =====================================================================

def create_http_session() -> requests.Session:
    retry = Retry(
        total=4,
        connect=4,
        read=4,
        status=4,
        backoff_factor=0.8,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "POST"}),
        respect_retry_after_header=True,
        raise_on_status=False,
    )

    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=20)
    session = requests.Session()
    session.headers.update({
        "User-Agent": "BioDSA-Chemistry-Toolkit/2.1",
        "Accept": "application/json",
    })
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


HTTP_SESSION = create_http_session()


def request_json(
    method: str,
    url: str,
    *,
    timeout: int = 15,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, Any]] = None,
    **kwargs
) -> Optional[Dict[str, Any]]:
    default_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) BioDSA/2.1"
    }
    if headers:
        default_headers.update(headers)
        
    try:
        resp = HTTP_SESSION.request(
            method, url, timeout=timeout, params=params, headers=default_headers, **kwargs
        )
        if resp.status_code == 200:
            return resp.json()
        elif resp.status_code != 404:
            # 404 是正常的“未查到数据”，只有其他真正的网络/服务器异常（如 500, 502, 403）才打印警告
            logger.warning("PubChem API HTTP %s | URL: %s", resp.status_code, url)
    except Exception as exc:
        logger.warning("PubChem request exception: %s", exc)
        
    return None

def get_json(
    url: str,
    *,
    timeout: int = 15,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, Any]] = None,
    **kwargs
) -> Optional[Dict[str, Any]]:
    return request_json("GET", url, timeout=timeout, params=params, headers=headers, **kwargs)


def post_json(
    url: str,
    *,
    data: Dict[str, Any],
    timeout: int = 15,
    params: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    return request_json("POST", url, data=data, timeout=timeout, params=params)


# =====================================================================
# Generic helpers
# =====================================================================

def require_rdkit() -> None:
    if not RDKIT_AVAILABLE:
        raise RuntimeError(
            "RDKit is required. Install it with: conda install -c conda-forge rdkit"
        )


@contextmanager
def suppress_rdkit_logs():
    if not RDKIT_AVAILABLE:
        yield
        return

    blocker = rdBase.BlockLogs()
    try:
        yield
    finally:
        del blocker


def mol_from_smiles_quiet(smiles: str):
    if not smiles:
        return None

    with suppress_rdkit_logs():
        try:
            return Chem.MolFromSmiles(str(smiles).strip())
        except Exception:
            return None


def is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, (list, tuple, dict, set)):
        return False

    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def to_jsonable(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    if isinstance(value, set):
        return sorted(to_jsonable(item) for item in value)

    if hasattr(value, "item"):
        try:
            value = value.item()
        except Exception:
            pass

    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if is_missing(value):
        return None
    if isinstance(value, (str, int, bool)):
        return value
    return str(value)


def make_json_safe_record(record: Dict[str, Any]) -> Dict[str, Any]:
    return {str(key): to_jsonable(value) for key, value in record.items()}


def save_json(data: Any, save_path: Optional[str]) -> None:
    if not save_path:
        return

    save_path = os.path.abspath(save_path)
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    temporary_path = save_path + ".tmp"

    with open(temporary_path, "w", encoding="utf-8") as file:
        json.dump(
            to_jsonable(data),
            file,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )

    os.replace(temporary_path, save_path)


# =====================================================================
# PubChem
# =====================================================================

PUBCHEM_PROPERTY_SETS = (
    "Title,IUPACName,MolecularFormula,CanonicalSMILES,IsomericSMILES",
)


def extract_pubchem_smiles(properties: dict) -> str:
    """全兼容提取 PubChem 返回的各种 SMILES 字段"""
    if not properties or not isinstance(properties, dict):
        return ""
    
    candidate_keys = [
        "IsomericSMILES", 
        "CanonicalSMILES", 
        "ConnectivitySMILES", 
        "SMILES"
    ]
    
    for key in candidate_keys:
        val = properties.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
            
    for k, v in properties.items():
        if "smiles" in k.lower() and isinstance(v, str) and v.strip():
            return v.strip()
            
    return ""


def extract_valid_cids(data: Optional[Dict[str, Any]]) -> List[int]:
    if not data:
        return []

    valid_cids = []
    for value in data.get("IdentifierList", {}).get("CID", []):
        try:
            cid = int(value)
        except (TypeError, ValueError):
            continue
        if cid > 0:
            valid_cids.append(cid)

    return valid_cids


def _first_pubchem_property(data: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not data or not isinstance(data, dict):
        return None
    props = data.get("PropertyTable", {}).get("Properties", [])
    return props[0] if props else None


def fetch_pubchem_properties_by_cid(cid: int) -> Optional[Dict[str, Any]]:
    if cid <= 0:
        return None

    base = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
    for fields in PUBCHEM_PROPERTY_SETS:
        data = get_json(
            f"{base}/compound/cid/{cid}/property/{fields}/JSON",
            timeout=20,
        )
        properties = _first_pubchem_property(data)
        if properties:
            return properties

    return None


def fetch_pubchem_properties_by_name(name: str) -> Optional[Dict[str, Any]]:
    if not name or not name.strip():
        return None

    base = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
    encoded_name = quote(name.strip())
    
    for fields in PUBCHEM_PROPERTY_SETS:
        data = get_json(
            f"{base}/compound/name/{encoded_name}/property/{fields}/JSON",
            timeout=20,
        )
        properties = _first_pubchem_property(data)
        if properties:
            return properties

    return None


def resolve_name_via_pubchem(
    identifier: str,
) -> Tuple[Optional[Any], str, str]:
    properties = fetch_pubchem_properties_by_name(identifier)
    if not properties:
        return None, "", "PubChem did not find a matching compound.\n"

    try:
        cid = int(properties.get("CID", 0))
    except (TypeError, ValueError):
        cid = 0

    if cid <= 0:
        return None, "", "PubChem returned no valid CID.\n"

    smiles = extract_pubchem_smiles(properties)
    if not smiles:
        return None, "", "PubChem returned no usable SMILES.\n"

    mol = mol_from_smiles_quiet(smiles)
    if mol is None:
        return None, "", "RDKit could not parse the PubChem structure.\n"

    log = f"**Resolved `{identifier}` through PubChem:** `{smiles}` (CID: {cid})\n"
    return mol, smiles, log


# =====================================================================
# Molecular standardization
# =====================================================================

def normalize_rdkit_mol(
    mol,
    *,
    parent_form: bool = True,
    neutralize: bool = True,
):
    require_rdkit()
    normalized = Chem.Mol(mol)

    with suppress_rdkit_logs():
        for atom in normalized.GetAtoms():
            atom.SetAtomMapNum(0)

        Chem.SanitizeMol(normalized)
        normalized = rdMolStandardize.Cleanup(normalized)

        if parent_form and len(Chem.GetMolFrags(normalized)) > 1:
            normalized = rdMolStandardize.FragmentParent(normalized)

        if neutralize:
            normalized = rdMolStandardize.Uncharger().uncharge(normalized)

        Chem.SanitizeMol(normalized)

    return normalized


def standardize_to_rdkit_mol(
    identifier: str,
    *,
    parent_form: bool = True,
    neutralize: bool = True,
) -> Tuple[Any, str, str]:
    require_rdkit()

    if identifier is None:
        return None, "", "⚠️ **Error:** Input cannot be None.\n"

    identifier = str(identifier).strip()
    if not identifier:
        return None, "", "⚠️ **Error:** Input cannot be empty.\n"

    info_log = ""
    mol = mol_from_smiles_quiet(identifier)

    if mol is None and SELFIES_AVAILABLE and "[" in identifier and "]" in identifier:
        try:
            decoded = sf.decoder(identifier)
            mol = mol_from_smiles_quiet(decoded)
            if mol is not None:
                info_log += f"**Decoded SELFIES:** `{decoded}`\n"
        except Exception as exc:
            logger.debug("SELFIES decoding failed: %s", exc)

    if mol is None:
        # 1. 拦截 InChIKey 并使用专用的 PubChem 接口
        clean_id = identifier.strip().upper()
        if re.match(r"^[A-Z]{14}-[A-Z]{10}-[A-Z]$", clean_id):
            info_log += f"*Detected InChIKey format. Resolving via PubChem InChIKey API...*\n"

            inchikey_data = get_json(
                f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/inchikey/{clean_id}/property/CanonicalSMILES,IsomericSMILES/JSON",
                timeout=15,
            )

            if inchikey_data and "PropertyTable" in inchikey_data:
                props = inchikey_data["PropertyTable"]["Properties"]
                if props:
                    resolved_smiles = extract_pubchem_smiles(props[0])
                    if resolved_smiles:
                        mol = mol_from_smiles_quiet(resolved_smiles)
                        if mol is not None:
                            info_log += (
                                f"**Resolved InChIKey to SMILES:** `{resolved_smiles}`\n"
                            )

            if mol is None:
                info_log += f"⚠️ **Failed to resolve InChIKey on PubChem.**\n"
                    
        # 2. 如果不是 InChIKey，再尝试作为通用名称(Name)去检索
        if mol is None:
            is_structural_formula = False
            if "Branch" in identifier or "Ring" in identifier or "Expl" in identifier:
                is_structural_formula = True
            elif " " not in identifier and (identifier.count("[") + identifier.count("=") + identifier.count("#")) >= 2:
                is_structural_formula = True
                
            if is_structural_formula:
                info_log += f"⚠️ **Skip PubChem resolution:** `{identifier}` looks like an invalid SMILES/SELFIES structure. Skipped name search to save time.\n"
            else:
                info_log += f"*Attempting PubChem name resolution for `{identifier}`...*\n"
                mol, _, pubchem_log = resolve_name_via_pubchem(identifier)
                info_log += pubchem_log

    if mol is None:
        return (
            None,
            "",
            info_log + f"⚠️ **Error:** Unable to parse or resolve `{identifier}`.\n",
        )

    try:
        original_fragments = len(Chem.GetMolFrags(mol))
        mol = normalize_rdkit_mol(
            mol, parent_form=parent_form, neutralize=neutralize
        )

        if parent_form and original_fragments > 1:
            info_log += (
                "*Multiple fragments detected; retained the parent fragment "
                "for database matching.*\n"
            )

        smiles = Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)
        return mol, smiles, info_log

    except Exception as exc:
        return (
            None,
            "",
            info_log + f"⚠️ **Error during molecular standardization:** {exc}\n",
        )


def mol_to_inchikey(mol) -> Optional[str]:
    if mol is None:
        return None

    try:
        with suppress_rdkit_logs():
            value = inchi.MolToInchiKey(mol)
    except Exception as exc:
        logger.debug("InChIKey generation failed: %s", exc)
        return None

    return str(value).strip().upper() or None if value else None


def smiles_to_inchikey(
    smiles: str,
    *,
    parent_form: bool,
    neutralize: bool,
) -> Optional[str]:
    mol = mol_from_smiles_quiet(smiles)
    if mol is None:
        return None

    try:
        mol = normalize_rdkit_mol(
            mol, parent_form=parent_form, neutralize=neutralize
        )
    except Exception:
        return None

    return mol_to_inchikey(mol)


def standardize_reaction_part(part_str: str) -> Tuple[str, List[str], str]:
    if not part_str:
        return "", [], ""

    frags_raw = [f.strip() for f in part_str.split(".") if f.strip()]
    canonical_smiles_list = []
    part_log = ""

    for frag in frags_raw:
        mol, smi, log = standardize_to_rdkit_mol(frag)
        if log:
            part_log += log
        if smi:
            canonical_smiles_list.append(smi)
        else:
            canonical_smiles_list.append(frag)

    sorted_unique = sorted(set(canonical_smiles_list))
    return ".".join(sorted_unique), sorted_unique, part_log


# =====================================================================
# Chemistry calculations
# =====================================================================

def analyze_functional_groups(mol) -> Dict[str, int]:
    require_rdkit()
    groups = {}

    for name, function in Fragments.fns:
        try:
            count = int(function(mol))
        except Exception as exc:
            logger.debug("Fragment descriptor %s failed: %s", name, exc)
            continue

        if count > 0:
            groups[name[3:] if name.startswith("fr_") else name] = count

    return groups


def estimate_nmr_peaks(mol) -> Tuple[int, int]:
    """估计对称性不同的 ¹H / ¹³C 环境；不是完整 NMR 模拟。"""
    require_rdkit()

    mol_h = Chem.AddHs(mol)
    ranks = list(
        Chem.CanonicalRankAtoms(mol_h, breakTies=False, includeChirality=True)
    )

    hydrogen_ranks = {
        ranks[atom.GetIdx()]
        for atom in mol_h.GetAtoms()
        if atom.GetAtomicNum() == 1
    }
    carbon_ranks = {
        ranks[atom.GetIdx()]
        for atom in mol_h.GetAtoms()
        if atom.GetAtomicNum() == 6
    }

    return len(hydrogen_ranks), len(carbon_ranks)


def extract_ghs_hazards(data: Any) -> List[str]:
    hazards = set()

    def walk(value):
        if isinstance(value, dict):
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
        elif isinstance(value, str):
            text = " ".join(value.split())
            if re.search(r"\bH\d{3}\b", text):
                hazards.add(text)

    walk(data)
    return sorted(hazards)


def extract_pubchem_annotations(data: Any) -> List[str]:
    """递归提取 PubChem PUG View JSON 中的真实文本内容"""
    results = []
    
    def walk(node):
        if isinstance(node, dict):
            if "StringWithMarkup" in node:
                for item in node["StringWithMarkup"]:
                    if "String" in item and item["String"]:
                        results.append(item["String"])
            elif "Number" in node:
                results.append(str(node["Number"]))
            else:
                for child in node.values():
                    walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(data)
    
    seen = set()
    unique_results = []
    for res in results:
        text = str(res).strip()
        if text and text not in seen:
            seen.add(text)
            unique_results.append(text)
            
    return unique_results


def fetch_pubchem_comprehensive(smiles: str) -> Dict[str, Any]:
    result = {
        "CID": None,
        "IUPACName": "",
        "Title": "",
        "MolecularFormula": "",
        "PubChemSMILES": "",
        "Hazards": [],
        "Synonyms": [],
    }

    base = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
    cid_data = post_json(
        f"{base}/compound/smiles/cids/JSON",
        data={"smiles": smiles},
        timeout=20,
    )

    cids = extract_valid_cids(cid_data)
    if not cids:
        return result

    cid = cids[0]
    result["CID"] = cid

    properties = fetch_pubchem_properties_by_cid(cid)
    if properties:
        result["IUPACName"] = properties.get("IUPACName") or ""
        result["Title"] = properties.get("Title") or ""
        result["MolecularFormula"] = properties.get("MolecularFormula") or ""
        result["PubChemSMILES"] = extract_pubchem_smiles(properties)

    synonym_data = get_json(f"{base}/compound/cid/{cid}/synonyms/JSON", timeout=20)
    synonym_rows = (
        synonym_data.get("InformationList", {}).get("Information", [])
        if synonym_data else []
    )
    if synonym_rows:
        result["Synonyms"] = [
            str(value) for value in synonym_rows[0].get("Synonym", [])[:20]
            if value
        ]

    result["ExperimentalProperties"] = {}
    
    target_headings = [
        "CAS", 
        "Melting Point", 
        "Boiling Point", 
        "Solubility", 
        "Dissociation Constants", 
        "Drug Indication",        
        "GHS Classification"      
    ]

    for heading in target_headings:
        url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/{cid}/JSON"
        
        data = get_json(
            url,
            params={"heading": heading},
            timeout=15,
        )
        
        if data:
            if heading == "GHS Classification":
                result["Hazards"] = extract_ghs_hazards(data)
            else:
                extracted_texts = extract_pubchem_annotations(data)
                if extracted_texts:
                    result["ExperimentalProperties"][heading] = extracted_texts[:3]

    return result


# =====================================================================
# LOTUS and QM9 indexes
# =====================================================================

_DATABASE_CACHE_LOCK = threading.RLock()


def find_first_column(
    available_columns: Iterable[str],
    candidates: Iterable[str],
) -> Optional[str]:
    available = set(available_columns)
    return next((name for name in candidates if name in available), None)


@lru_cache(maxsize=4)
def _load_lotus_index(
    csv_path: str,
    file_mtime_ns: int,
) -> Dict[str, Dict[str, Any]]:
    del file_mtime_ns

    if not os.path.isfile(csv_path):
        return {}

    try:
        columns = list(pd.read_csv(csv_path, nrows=0).columns)
    except Exception as exc:
        logger.warning("Unable to read LOTUS header: %s", exc)
        return {}

    smiles_col = find_first_column(
        columns, ("structure_smiles", "smiles", "SMILES")
    )
    key_col = find_first_column(
        columns,
        ("structure_inchikey", "structure_inchi_key",
         "inchikey", "inchi_key", "InChIKey"),
    )
    class_col = find_first_column(
        columns,
        ("structure_taxonomy_classyfire_03class", "classyfire_class"),
    )

    if not smiles_col and not key_col:
        logger.warning("LOTUS has no SMILES or InChIKey column.")
        return {}

    usecols = list(dict.fromkeys(
        column for column in (smiles_col, key_col, class_col) if column
    ))
    index = {}

    try:
        chunks = pd.read_csv(
            csv_path, usecols=usecols, chunksize=50_000, low_memory=False
        )

        for chunk in chunks:
            for record in chunk.to_dict(orient="records"):
                key = None

                if key_col and not is_missing(record.get(key_col)):
                    key = str(record[key_col]).strip().upper() or None

                if not key and smiles_col and not is_missing(record.get(smiles_col)):
                    key = smiles_to_inchikey(
                        str(record[smiles_col]),
                        parent_form=True,
                        neutralize=True,
                    )

                if key and key not in index:
                    index[key] = make_json_safe_record(record)

    except Exception as exc:
        logger.warning("Unable to build LOTUS index: %s", exc)
        return {}

    logger.info("Loaded %d LOTUS InChIKey records.", len(index))
    return index


def get_lotus_index() -> Dict[str, Dict[str, Any]]:
    if not os.path.isfile(LOTUS_CSV_PATH):
        return {}

    with _DATABASE_CACHE_LOCK:
        return _load_lotus_index(
            LOTUS_CSV_PATH, os.stat(LOTUS_CSV_PATH).st_mtime_ns
        )


def search_lotus(mol) -> Optional[Dict[str, Any]]:
    key = mol_to_inchikey(mol)
    record = get_lotus_index().get(key) if key else None
    return dict(record) if record is not None else None


@lru_cache(maxsize=4)
def _load_qm9_index(
    csv_path: str,
    file_mtime_ns: int,
) -> Dict[str, Dict[str, Any]]:
    del file_mtime_ns

    if not os.path.isfile(csv_path):
        return {}

    try:
        columns = list(pd.read_csv(csv_path, nrows=0).columns)
    except Exception as exc:
        logger.warning("Unable to read QM9 header: %s", exc)
        return {}

    smiles_col = find_first_column(columns, ("smiles", "SMILES"))
    key_col = find_first_column(columns, ("inchikey", "inchi_key", "InChIKey"))

    if not smiles_col and not key_col:
        logger.warning("QM9 has no SMILES or InChIKey column.")
        return {}

    index = {}

    try:
        chunks = pd.read_csv(csv_path, chunksize=50_000, low_memory=False)

        for chunk in chunks:
            for record in chunk.to_dict(orient="records"):
                key = None

                if key_col and not is_missing(record.get(key_col)):
                    key = str(record[key_col]).strip().upper() or None

                if not key and smiles_col and not is_missing(record.get(smiles_col)):
                    mol = mol_from_smiles_quiet(str(record[smiles_col]))
                    if mol is not None:
                        key = mol_to_inchikey(mol)

                if key and key not in index:
                    index[key] = make_json_safe_record(record)

    except Exception as exc:
        logger.warning("Unable to build QM9 index: %s", exc)
        return {}

    logger.info("Loaded %d QM9 InChIKey records.", len(index))
    return index


def get_qm9_index() -> Dict[str, Dict[str, Any]]:
    if not os.path.isfile(QM9_CSV_PATH):
        return {}

    with _DATABASE_CACHE_LOCK:
        return _load_qm9_index(
            QM9_CSV_PATH, os.stat(QM9_CSV_PATH).st_mtime_ns
        )


def search_qm9(mol) -> Optional[Dict[str, Any]]:
    key = mol_to_inchikey(mol)
    record = get_qm9_index().get(key) if key else None
    return dict(record) if record is not None else None


def clear_database_caches() -> None:
    with _DATABASE_CACHE_LOCK:
        _load_lotus_index.cache_clear()
        _load_qm9_index.cache_clear()


def resolve_iupac_to_smiles(identifier: str) -> str:
    """使用 OPSIN API 将 IUPAC 名字翻译为 SMILES。"""
    if "1" in identifier or "=" in identifier or identifier.count("-") >= 2:
        return identifier
        
    opsin_url = f"https://opsin.ch.cam.ac.uk/opsin/{quote(identifier)}.smi"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) BioDSA/1.0"}
    try:
        response = requests.get(opsin_url, headers=headers, timeout=10)
        if response.status_code == 200 and response.text:
            return response.text.strip()
    except Exception:
        pass
        
    return identifier


# =====================================================================
# Fast molecular profile
# =====================================================================

def fetch_molecule_profile_fast(
    identifier: str,
    save_path: Optional[str] = None,
) -> Tuple[Dict[str, Any], str]:
    output = f"# Chemical Molecule Profile\n\n## Input: `{identifier}`\n\n"
    results = {}

    smiles_candidate = resolve_iupac_to_smiles(identifier)
    if smiles_candidate != identifier:
        output += f"*Successfully resolved IUPAC name to SMILES via OPSIN:* `{smiles_candidate}`\n"
        identifier = smiles_candidate

    try:
        mol, smiles, parse_log = standardize_to_rdkit_mol(
            identifier, parent_form=True, neutralize=True
        )
    except RuntimeError as exc:
        results["error"] = str(exc)
        output += f"⚠️ **Dependency error:** {exc}\n"
        save_json(results, save_path)
        return results, output

    output += parse_log
    if mol is None:
        results["error"] = "Unable to parse or resolve input."
        save_json(results, save_path)
        return results, output
    
    try:
        selfies_str = sf.encoder(smiles)
    except Exception:
        selfies_str = "N/A (Encoding failed)"

    molecular_weight = float(Descriptors.MolWt(mol))
    exact_mass = float(rdMolDescriptors.CalcExactMolWt(mol))
    logp = float(Descriptors.MolLogP(mol))
    hbd = int(Descriptors.NumHDonors(mol))
    hba = int(Descriptors.NumHAcceptors(mol))
    rotatable_bonds = int(Descriptors.NumRotatableBonds(mol))
    tpsa = float(Descriptors.TPSA(mol))
    qed_value = float(QED.qed(mol))
    formula = rdMolDescriptors.CalcMolFormula(mol)
    key = mol_to_inchikey(mol)

    lipinski_violations = sum((
        molecular_weight > 500, logp > 5, hbd > 5, hba > 10
    ))
    n1h, n13c = estimate_nmr_peaks(mol)
    functional_groups = analyze_functional_groups(mol)

    results.update({
        "input": identifier,
        "canonical_smiles": smiles,
        "selfies": selfies_str,
        "inchikey": key,
        "molecular_formula": formula,
        "physicochemical": {
            "molecular_weight": molecular_weight,
            "exact_mass": exact_mass,
            "logp": logp,
            "tpsa": tpsa,
            "hbd": hbd,
            "hba": hba,
            "rotatable_bonds": rotatable_bonds,
            "lipinski_violations": int(lipinski_violations),
            "qed": qed_value,
        },
        "estimated_nmr_environments": {"1H": n1h, "13C": n13c},
        "functional_groups": functional_groups,
    })

    output += (
        "### 1. Physicochemical properties\n"
        f"- **Canonical SMILES:** `{smiles}`\n"
        f"- **SELFIES:** `{selfies_str}`\n"
        f"- **InChIKey:** `{key or 'N/A'}`\n"
        f"- **Molecular Formula:** {formula}\n"
        f"- **Molecular Weight:** {molecular_weight:.2f} g/mol\n"
        f"- **Exact Mass:** {exact_mass:.5f} Da\n"
        f"- **LogP:** {logp:.2f}\n"
        f"- **TPSA:** {tpsa:.2f} Å²\n"
        f"- **HBD / HBA:** {hbd} / {hba}\n"
        f"- **Rotatable Bonds:** {rotatable_bonds}\n"
        f"- **Lipinski Violations:** {lipinski_violations}\n"
        f"- **QED:** {qed_value:.3f}\n\n"
        "### 2. Estimated spectroscopy\n"
        f"- **Estimated distinct ¹H environments:** {n1h}\n"
        f"- **Estimated distinct ¹³C environments:** {n13c}\n"
        "- *These are symmetry-based estimates, not predicted spectra.*\n\n"
        "### 3. Functional groups\n"
    )

    if functional_groups:
        for name, count in sorted(functional_groups.items()):
            output += f"- **{name}:** {count}\n"
    else:
        output += "- No RDKit fragment descriptors detected.\n"

    pubchem_info = fetch_pubchem_comprehensive(smiles)
    results["pubchem"] = pubchem_info
    output += "\n### 4. PubChem and safety\n"

    if pubchem_info.get("CID"):
        output += (
            f"- **PubChem CID:** {pubchem_info['CID']}\n"
            f"- **IUPAC Name:** {pubchem_info.get('IUPACName') or 'N/A'}\n"
        )
        properties = pubchem_info.get("ExperimentalProperties", {})
        if properties:
            output += "- **Experimental Data & Pharmacopeia:**\n"
            for prop_name, prop_values in properties.items():
                output += f"  - **{prop_name}:** {prop_values[0]}\n"
    else:
        output += "- No valid PubChem record found.\n"

    output += (
        "\n> Safety data is informational only. Consult an official "
        "supplier SDS before handling a chemical.\n\n"
    )

    lotus_record = search_lotus(mol)
    results["lotus"] = lotus_record

    if lotus_record:
        classyfire = (
            lotus_record.get("structure_taxonomy_classyfire_03class")
            or lotus_record.get("classyfire_class")
            or "N/A"
        )
        output += (
            "### 5. LOTUS\n"
            "- **Found:** Yes\n"
            f"- **ClassyFire class:** {classyfire}\n"
        )

    save_json(results, save_path)
    return results, output


# =====================================================================
# ChEMBL
# =====================================================================

CHEMBL_PHASE_LABELS = {
    -1.0: "Unknown / Not applicable",
    0.0: "Preclinical / Not assigned",
    0.5: "Early clinical / Phase 0.5",
    1.0: "Phase I",
    2.0: "Phase II",
    3.0: "Phase III",
    4.0: "Approved",
}


def parse_chembl_phase(value: Any) -> Tuple[Optional[float], str]:
    try:
        phase = float(value)
    except (TypeError, ValueError):
        return None, "Unknown"

    return (
        phase,
        CHEMBL_PHASE_LABELS.get(phase, f"Unrecognized phase value ({phase:g})"),
    )


def fetch_chembl_target_bioactivity(
    identifier: str,
    save_path: Optional[str] = None,
    activity_limit: int = 500,
    hiv_only: bool = False,
) -> Tuple[Dict[str, Any], str]:

    output = (
        f"# ChEMBL Bioactivity & Target Profile\n\n"
        f"## Input: `{identifier}`\n\n"
    )

    results: Dict[str, Any] = {}
    base = "https://www.ebi.ac.uk/chembl/api/data"

    identifier = str(identifier).strip()
    is_inchikey_input = bool(re.match(r"^[A-Z]{14}-[A-Z]{10}-[A-Z]$", identifier.upper()))

    if is_inchikey_input:
        key = identifier.upper()
        smiles = "N/A"
        output += f"*Input identified directly as InChIKey: `{key}`. Skipping RDKit standardization.*\n\n"
    else:
        try:
            mol, smiles, parse_log = standardize_to_rdkit_mol(
                identifier,
                parent_form=True,
                neutralize=True,
            )
        except RuntimeError as exc:
            results["error"] = str(exc)
            output += f"⚠️ **Dependency error:** {exc}\n"
            save_json(results, save_path)
            return results, output

        output += parse_log

        if mol is None:
            results["error"] = "Unable to parse or resolve input."
            save_json(results, save_path)
            return results, output

        key = mol_to_inchikey(mol)
        if not key:
            results["error"] = "Unable to generate InChIKey."
            output += "⚠️ Unable to generate an InChIKey.\n"
            save_json(results, save_path)
            return results, output

    molecule_data = get_json(
        f"{base}/molecule.json",
        params={
            "molecule_structures__standard_inchi_key": key,
            "limit": 20,
        },
        timeout=20,
    )

    molecules = molecule_data.get("molecules", []) if molecule_data else []

    exact_matches = [
        candidate for candidate in molecules
        if ((candidate.get("molecule_structures") or {})
            .get("standard_inchi_key", "").strip().upper() == key.upper())
    ]

    if not exact_matches:
        results.update({
            "canonical_smiles": smiles,
            "inchikey": key,
            "exact_inchikey_match": False,
            "hiv_evidence_summary": {
                "status": "NO_EXACT_CHEMBL_MOLECULE",
                "evidence_available": False,
                "hiv_related_activity_found": False,
            },
        })

        output += (
            f"⚠️ **No exact ChEMBL InChIKey match:** `{key}`\n\n"
            "No exact compound-level ChEMBL bioactivity evidence can be retrieved.\n"
        )
        save_json(results, save_path)
        return results, output

    molecule_record = exact_matches[0]

    if smiles == "N/A":
        smiles = (molecule_record.get("molecule_structures") or {}).get("canonical_smiles", "N/A")

    chembl_id = molecule_record.get("molecule_chembl_id")
    preferred_name = molecule_record.get("pref_name") or "N/A"
    phase_value, phase_label = parse_chembl_phase(molecule_record.get("max_phase"))

    results.update({
        "canonical_smiles": smiles,
        "inchikey": key,
        "chembl_id": chembl_id,
        "preferred_name": preferred_name,
        "max_phase": phase_value,
        "max_phase_label": phase_label,
        "exact_inchikey_match": True,
        "molecule_record": molecule_record,
    })

    output += (
        "### Basic information\n"
        f"- **Canonical SMILES:** `{smiles}`\n"
        f"- **InChIKey:** `{key}`\n"
        f"- **ChEMBL ID:** {chembl_id}\n"
        f"- **Preferred Name:** {preferred_name}\n"
        f"- **Maximum Phase:** {phase_label}\n\n"
    )

    mechanism_data = get_json(
        f"{base}/mechanism.json",
        params={"molecule_chembl_id": chembl_id, "limit": 100},
        timeout=20,
    )

    mechanisms = mechanism_data.get("mechanisms", []) if mechanism_data else []
    results["mechanisms"] = mechanisms

    if mechanisms:
        output += "### Mechanisms and targets\n"
        for mechanism in mechanisms:
            output += (
                f"- **Target:** {mechanism.get('target_pref_name') or 'Unknown'} "
                f"({mechanism.get('target_chembl_id') or 'N/A'})\n"
                f"  - **Action Type:** {mechanism.get('action_type') or 'N/A'}\n"
                f"  - **Mechanism:** {mechanism.get('mechanism_of_action') or 'N/A'}\n"
            )
        output += "\n"
    else:
        output += "*No mechanism-of-action records were found.*\n\n"

    activity_data = get_json(
        f"{base}/activity.json",
        params={"molecule_chembl_id": chembl_id, "limit": activity_limit},
        timeout=30,
    )

    activities = activity_data.get("activities", []) if activity_data else []
    results["activity_count"] = len(activities)

    activity_records: List[Dict[str, Any]] = []
    
    for activity in activities:
        record = {
            "activity_id": activity.get("activity_id"),
            "assay_chembl_id": activity.get("assay_chembl_id"),
            "target_pref_name": activity.get("target_pref_name"),
            "target_organism": activity.get("target_organism"),
            "assay_type": activity.get("assay_type"),
            "assay_description": activity.get("assay_description"),
            "standard_type": activity.get("standard_type"),
            "standard_relation": activity.get("standard_relation"),
            "standard_value": activity.get("standard_value"),
            "standard_units": activity.get("standard_units"),
            "pchembl_value": activity.get("pchembl_value"),
            "activity_comment": activity.get("activity_comment"),
            "bao_label": activity.get("bao_label"),
        }
        activity_records.append(record)

    hiv_keywords = [
        "hiv", "hiv-1", "hiv1", "human immunodeficiency virus",
        "viral replication", "virus replication", "viral infection",
        "antiviral", "anti-hiv", "anti hiv", "reverse transcriptase",
        "integrase", "protease", "gp120", "gp41", "entry inhibitor", "viral entry",
    ]

    def contains_hiv_keyword(text: str) -> bool:
        if not text: return False
        text = text.lower()
        return any(keyword in text for keyword in hiv_keywords)

    hiv_activities = []
    for activity in activity_records:
        searchable_text = " ".join(
            str(activity.get(field) or "")
            for field in [
                "target_pref_name", "target_organism", "assay_type",
                "assay_description", "activity_comment", "bao_label",
            ]
        )
        if contains_hiv_keyword(searchable_text):
            activity_copy = dict(activity)
            activity_copy["hiv_keyword_match"] = True
            hiv_activities.append(activity_copy)

    if hiv_only:
        results["activities"] = hiv_activities
    else:
        results["activities"] = activity_records
        results["hiv_related_activities"] = hiv_activities

    active_hiv = []
    inactive_hiv = []
    quantitative_hiv = []

    for activity in hiv_activities:
        value = activity.get("standard_value")
        comment = (activity.get("activity_comment") or "").lower()

        if any(word in comment for word in ["inactive", "not active", "no activity"]):
            inactive_hiv.append(activity)
            continue

        if any(word in comment for word in ["active", "potent", "inhibit", "inhibition"]):
            active_hiv.append(activity)
            continue

        if value is not None:
            try:
                val_float = float(value)
                relation = activity.get("standard_relation") or "="
                
                if relation in [">", ">="] and val_float >= 10000:
                    inactive_hiv.append(activity)
                else:
                    active_hiv.append(activity)
            except (ValueError, TypeError):
                quantitative_hiv.append(activity)

    if hiv_activities:
        if active_hiv and not inactive_hiv:
            hiv_status = "HIV_RELATED_ACTIVITY_FOUND"
        elif inactive_hiv and not active_hiv:
            hiv_status = "HIV_RELATED_INACTIVE_EVIDENCE_FOUND"
        else:
            hiv_status = "MIXED_HIV_ACTIVITY_EVIDENCE"
    else:
        hiv_status = "NO_HIV_RELATED_ACTIVITY_FOUND"

    results["hiv_evidence_summary"] = {
        "status": hiv_status,
        "evidence_available": bool(hiv_activities),
        "hiv_related_activity_count": len(hiv_activities),
        "active_evidence_count": len(active_hiv),
        "inactive_evidence_count": len(inactive_hiv),
        "search_keywords": hiv_keywords,
    }

    output += (
        "### Bioactivity summary\n"
        f"- **Total activity records retrieved:** {len(activities)}\n"
        f"- **HIV-related activity records:** {len(hiv_activities)}\n"
        f"- **HIV evidence status:** `{hiv_status}`\n\n"
    )

    if hiv_activities:
        output += "### HIV-related activity evidence\n"
        for i, activity in enumerate(hiv_activities[:20], start=1):
            target = activity.get('target_pref_name') or 'Unknown'
            org = activity.get('target_organism') or 'Unknown'
            desc = activity.get('assay_description') or 'N/A'
            val_str = f"{activity.get('standard_relation') or ''} {activity.get('standard_value') or ''} {activity.get('standard_units') or ''}".strip()
            if not val_str: val_str = "N/A"
            
            output += (
                f"\n#### HIV evidence #{i}\n"
                f"- **Target:** {target} ({org})\n"
                f"- **Assay:** {desc}\n"
                f"- **Type:** {activity.get('standard_type') or 'N/A'}\n"
                f"- **Value:** {val_str}\n"
                f"- **Comment:** {activity.get('activity_comment') or 'None'}\n"
            )
        if len(hiv_activities) > 20:
            output += f"\n*(Showing top 20 out of {len(hiv_activities)} HIV-related records)*\n"
    else:
        output += "*No HIV-related activity records were identified from the retrieved data.*\n"

    save_json(results, save_path)
    return results, output


# =====================================================================
# PySCF DFT
# =====================================================================

def infer_charge_and_spin(mol) -> Tuple[int, int]:
    charge = int(Chem.GetFormalCharge(mol))
    nuclear_charge = sum(atom.GetAtomicNum() for atom in mol.GetAtoms())
    electron_count = nuclear_charge - charge
    radical_electrons = sum(
        atom.GetNumRadicalElectrons() for atom in mol.GetAtoms()
    )

    spin = radical_electrons if radical_electrons else electron_count % 2
    if (electron_count + spin) % 2:
        spin = electron_count % 2

    if spin < 0 or spin > electron_count:
        raise ValueError(
            f"Invalid spin={spin} for electron_count={electron_count}."
        )

    return charge, spin


def analyze_mo_occupations(mo_energy: Any, mo_occ: Any) -> Dict[str, Any]:
    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("NumPy is required for orbital analysis.") from exc

    energies = np.asarray(mo_energy)
    occupations = np.asarray(mo_occ)

    if energies.ndim == 1:
        channel_data = [("restricted", energies, occupations)]
    elif energies.ndim == 2 and energies.shape[0] == 2:
        channel_data = [
            ("alpha", energies[0], occupations[0]),
            ("beta", energies[1], occupations[1]),
        ]
    else:
        raise RuntimeError(f"Unexpected MO energy shape: {energies.shape}")

    all_occupied = []
    all_virtual = []
    channels = []

    for name, channel_energy, channel_occ in channel_data:
        occupied = channel_energy[channel_occ > 1e-8]
        virtual = channel_energy[channel_occ <= 1e-8]

        homo = float(np.max(occupied)) if len(occupied) else None
        lumo = float(np.min(virtual)) if len(virtual) else None

        channels.append({
            "channel": name,
            "occupied_orbitals": int(len(occupied)),
            "virtual_orbitals": int(len(virtual)),
            "homo_hartree": homo,
            "lumo_hartree": lumo,
            "gap_hartree": lumo - homo if homo is not None and lumo is not None else None,
        })

        all_occupied.extend(float(value) for value in occupied)
        all_virtual.extend(float(value) for value in virtual)

    if not all_occupied or not all_virtual:
        raise RuntimeError("Unable to identify occupied and virtual orbitals.")

    homo = max(all_occupied)
    lumo = min(all_virtual)

    return {
        "homo_hartree": homo,
        "lumo_hartree": lumo,
        "gap_hartree": lumo - homo,
        "channels": channels,
    }


def compute_pyscf_dft(
    mol,
    *,
    charge: Optional[int] = None,
    spin: Optional[int] = None,
) -> Dict[str, Any]:
    try:
        from pyscf import dft, gto
    except ImportError as exc:
        raise RuntimeError(
            "PySCF is not installed. Install it with: pip install pyscf"
        ) from exc

    mol_h = Chem.AddHs(Chem.Mol(mol))
    parameters = AllChem.ETKDGv3()
    parameters.randomSeed = 42
    parameters.useRandomCoords = True

    if AllChem.EmbedMolecule(mol_h, parameters) != 0:
        raise RuntimeError("RDKit 3D conformer embedding failed.")

    if AllChem.MMFFHasAllMoleculeParams(mol_h):
        optimization_status = AllChem.MMFFOptimizeMolecule(mol_h, maxIters=500)
    else:
        optimization_status = AllChem.UFFOptimizeMolecule(mol_h, maxIters=500)

    if optimization_status < 0:
        logger.warning("RDKit geometry optimization failed.")

    inferred_charge, inferred_spin = infer_charge_and_spin(mol_h)
    charge = inferred_charge if charge is None else int(charge)
    spin = inferred_spin if spin is None else int(spin)

    electron_count = (
        sum(atom.GetAtomicNum() for atom in mol_h.GetAtoms()) - charge
    )
    if spin < 0 or spin > electron_count or (electron_count + spin) % 2:
        raise ValueError(
            f"Incompatible electron count and spin: "
            f"electrons={electron_count}, spin={spin}."
        )

    conformer = mol_h.GetConformer()
    atom_lines = []

    for atom in mol_h.GetAtoms():
        position = conformer.GetAtomPosition(atom.GetIdx())
        atom_lines.append(
            f"{atom.GetSymbol()} "
            f"{position.x:.8f} {position.y:.8f} {position.z:.8f}"
        )

    pyscf_mol = gto.M(
        atom="\n".join(atom_lines),
        basis="6-31g*",
        charge=charge,
        spin=spin,
        unit="Angstrom",
        verbose=0,
    )

    mean_field = dft.RKS(pyscf_mol) if spin == 0 else dft.UKS(pyscf_mol)
    mean_field.xc = "b3lyp"
    total_energy = float(mean_field.kernel())

    mo_result = analyze_mo_occupations(
        mean_field.mo_energy, mean_field.mo_occ
    )
    dipole_vector = [
        float(value) for value in mean_field.dip_moment(unit="Debye", verbose=0)
    ]

    return {
        "method": "B3LYP/6-31G*",
        "reference": "RKS" if spin == 0 else "UKS",
        "charge": charge,
        "spin": spin,
        "multiplicity": spin + 1,
        "electron_count": electron_count,
        "converged": bool(mean_field.converged),
        "total_energy_hartree": total_energy,
        **mo_result,
        "dipole_vector_debye": dipole_vector,
        "dipole_debye": math.sqrt(sum(value ** 2 for value in dipole_vector)),
    }


def compute_quantum_properties_slow(
    smiles: str,
    save_path: Optional[str] = None,
    *,
    charge: Optional[int] = None,
    spin: Optional[int] = None,
) -> Tuple[Dict[str, Any], str]:
    output = f"# Quantum Chemical Properties\n\n## Input: `{smiles}`\n\n"
    results = {}

    try:
        mol, canonical_smiles, parse_log = standardize_to_rdkit_mol(
            smiles, parent_form=False, neutralize=False
        )
    except RuntimeError as exc:
        results["error"] = str(exc)
        output += f"⚠️ **Dependency error:** {exc}\n"
        save_json(results, save_path)
        return results, output

    output += parse_log
    if mol is None:
        results["error"] = "Unable to parse or resolve input."
        save_json(results, save_path)
        return results, output

    results.update({
        "canonical_smiles": canonical_smiles,
        "inchikey": mol_to_inchikey(mol),
    })

    qm9_record = search_qm9(mol) if charge is None and spin is None else None

    if qm9_record:
        results["source"] = "QM9"
        results["qm9"] = qm9_record
        output += "### Source: QM9 InChIKey match\n"

        for key, label, unit in (
            ("homo", "HOMO", "Hartree"),
            ("lumo", "LUMO", "Hartree"),
            ("mu", "Dipole Moment", "Debye"),
        ):
            value = qm9_record.get(key)
            if value is not None:
                output += f"- **{label}:** {value} {unit}\n"

    else:
        output += (
            "*No QM9 match was found, or explicit charge/spin was provided. "
            "Running PySCF B3LYP/6-31G\\*...*\n\n"
        )

        try:
            dft_result = compute_pyscf_dft(mol, charge=charge, spin=spin)
            results["source"] = "PySCF"
            results["dft"] = dft_result

            output += (
                "### PySCF result\n"
                f"- **Reference:** {dft_result['reference']}\n"
                f"- **Charge:** {dft_result['charge']}\n"
                f"- **Multiplicity:** {dft_result['multiplicity']}\n"
                f"- **Converged:** {'Yes' if dft_result['converged'] else 'No'}\n"
                f"- **Total Energy:** {dft_result['total_energy_hartree']:.8f} Hartree\n"
                f"- **HOMO:** {dft_result['homo_hartree']:.6f} Hartree\n"
                f"- **LUMO:** {dft_result['lumo_hartree']:.6f} Hartree\n"
                f"- **HOMO-LUMO Gap:** {dft_result['gap_hartree']:.6f} Hartree\n"
                f"- **Dipole Moment:** {dft_result['dipole_debye']:.4f} Debye\n"
            )

            if not dft_result["converged"]:
                output += "\n> Warning: SCF did not fully converge.\n"

        except Exception as exc:
            logger.exception("DFT computation failed.")
            results["source"] = "PySCF"
            results["error"] = str(exc)
            output += f"⚠️ **DFT computation failed:** {exc}\n"

    save_json(results, save_path)
    return results, output


# =====================================================================
# ORD product index
# =====================================================================

_ORD_INDEX_LOCK = threading.Lock()
ORD_INDEX_VERSION = "2"


def canonical_reaction_product(reaction_smiles: str) -> Optional[str]:
    require_rdkit()

    if not reaction_smiles or ">" not in reaction_smiles:
        return None

    product_smiles = reaction_smiles.rsplit(">", 1)[-1].strip()
    if not product_smiles:
        return None

    with suppress_rdkit_logs():
        try:
            mol = Chem.MolFromSmiles(product_smiles)
            if mol is None:
                return None

            for atom in mol.GetAtoms():
                atom.SetAtomMapNum(0)

            return Chem.MolToSmiles(
                mol, canonical=True, isomericSmiles=True
            )
        except Exception:
            return None


def _reaction_exact_hash(reaction_smiles: str) -> bytes:
    return hashlib.sha256(reaction_smiles.encode("utf-8")).digest()


def _ord_index_is_current(index_path: str) -> bool:
    if not os.path.isfile(index_path) or not os.path.isfile(ORD_DB_PATH):
        return False

    source_stat = os.stat(ORD_DB_PATH)

    try:
        uri = f"file:{os.path.abspath(index_path)}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True, timeout=20)) as connection:
            metadata = dict(
                connection.execute("SELECT key, value FROM metadata")
            )

        return (
            metadata.get("index_version") == ORD_INDEX_VERSION
            and metadata.get("source_size") == str(source_stat.st_size)
            and metadata.get("source_mtime_ns") == str(source_stat.st_mtime_ns)
        )
    except (OSError, sqlite3.Error):
        return False


def _has_useful_conditions(
    temperature: Any,
    time_hours: Any,
    solvents: Any,
) -> int:
    if temperature is not None or time_hours is not None:
        return 1

    if solvents is None:
        return 0

    return int(str(solvents).strip() not in ("", "[]", "{}", "null", "None"))


def ensure_ord_product_index() -> str:
    require_rdkit()

    if not os.path.isfile(ORD_DB_PATH):
        raise FileNotFoundError(ORD_DB_PATH)

    with _ORD_INDEX_LOCK:
        if _ord_index_is_current(ORD_PRODUCT_INDEX_PATH):
            return ORD_PRODUCT_INDEX_PATH

        logger.info("Building ORD index from %s", ORD_DB_PATH)

        index_dir = os.path.dirname(os.path.abspath(ORD_PRODUCT_INDEX_PATH))
        os.makedirs(index_dir, exist_ok=True)

        temp_path = (
            f"{ORD_PRODUCT_INDEX_PATH}."
            f"{os.getpid()}.{threading.get_ident()}.tmp"
        )
        source_stat = os.stat(ORD_DB_PATH)

        try:
            with (
                closing(sqlite3.connect(ORD_DB_PATH, timeout=60)) as source_conn,
                closing(sqlite3.connect(temp_path, timeout=60)) as index_conn,
            ):
                index_conn.execute("PRAGMA journal_mode=DELETE")
                index_conn.execute("PRAGMA synchronous=OFF")

                index_conn.execute("""
                    CREATE TABLE products (
                        product_key TEXT NOT NULL,
                        reaction_id TEXT NOT NULL,
                        exact_hash BLOB NOT NULL,
                        has_conditions INTEGER NOT NULL
                    )
                """)
                index_conn.execute("""
                    CREATE TABLE metadata (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    )
                """)

                cursor = source_conn.execute("""
                    SELECT reaction_id, reaction_smiles, target_product_smiles, yield_percent,
                           temperature_celsius, time_hours, solvents
                    FROM reaction_conditions
                """)

                batch = []
                scanned = 0
                indexed = 0

                for reaction_id, reaction_smiles, temp, hours, solvents in cursor:
                    scanned += 1
                    if not reaction_id or not reaction_smiles:
                        continue

                    product_key = canonical_reaction_product(reaction_smiles)
                    if not product_key:
                        continue

                    batch.append((
                        product_key,
                        reaction_id,
                        _reaction_exact_hash(reaction_smiles),
                        _has_useful_conditions(temp, hours, solvents),
                    ))

                    if len(batch) >= 10_000:
                        index_conn.executemany(
                            "INSERT INTO products VALUES (?, ?, ?, ?)", batch
                        )
                        indexed += len(batch)
                        batch.clear()

                    if scanned % 100_000 == 0:
                        logger.info(
                            "ORD index progress: scanned=%d, indexed=%d",
                            scanned, indexed,
                        )

                if batch:
                    index_conn.executemany(
                        "INSERT INTO products VALUES (?, ?, ?, ?)", batch
                    )
                    indexed += len(batch)

                index_conn.execute("""
                    CREATE INDEX idx_products_key
                    ON products (product_key, has_conditions DESC)
                """)
                index_conn.execute("""
                    CREATE INDEX idx_products_exact
                    ON products (exact_hash, has_conditions DESC)
                """)

                final_stat = os.stat(ORD_DB_PATH)
                if (
                    final_stat.st_size != source_stat.st_size
                    or final_stat.st_mtime_ns != source_stat.st_mtime_ns
                ):
                    raise RuntimeError(
                        "ORD database changed while building the index. Retry."
                    )

                index_conn.executemany(
                    "INSERT INTO metadata VALUES (?, ?)",
                    [
                        ("index_version", ORD_INDEX_VERSION),
                        ("source_size", str(source_stat.st_size)),
                        ("source_mtime_ns", str(source_stat.st_mtime_ns)),
                    ],
                )
                index_conn.commit()

            os.replace(temp_path, ORD_PRODUCT_INDEX_PATH)
            logger.info("ORD index complete: scanned=%d, indexed=%d", scanned, indexed)

        except Exception:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise

        return ORD_PRODUCT_INDEX_PATH


def _fetch_ord_rows_by_ids(
    connection: sqlite3.Connection,
    reaction_ids: List[str],
) -> List[sqlite3.Row]:
    if not reaction_ids:
        return []

    placeholders = ",".join("?" for _ in reaction_ids)
    rows = connection.execute(
        f"""
        SELECT reaction_id, reaction_smiles, target_product_smiles, yield_percent,
               temperature_celsius, time_hours, solvents
        FROM reaction_conditions
        WHERE reaction_id IN ({placeholders})
        """,
        reaction_ids,
    ).fetchall()

    by_id = {row["reaction_id"]: row for row in rows}
    return [by_id[rid] for rid in reaction_ids if rid in by_id]


def parse_solvents(value: Any) -> List[str]:
    if value is None:
        return []

    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]

    if isinstance(value, dict):
        solvents = []
        for key, item in value.items():
            if isinstance(item, str) and item.strip():
                solvents.append(item.strip())
            elif isinstance(key, str) and key.strip():
                solvents.append(key.strip())
        return solvents

    if isinstance(value, str):
        value = value.strip()
        if not value:
            return []

        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return [
                part.strip()
                for part in re.split(r"[;,]", value)
                if part.strip()
            ]

        if isinstance(parsed, (list, dict)):
            return parse_solvents(parsed)
        if isinstance(parsed, str):
            return [parsed.strip()] if parsed.strip() else []

    text = str(value).strip()
    return [text] if text else []


def canonicalize_and_sort_smiles(smiles_str: str) -> Tuple[str, List[str]]:
    if not smiles_str:
        return "", []

    fragments = [f.strip() for f in smiles_str.split(".") if f.strip()]
    clean_fragments = []

    try:
        from rdkit import Chem
        for frag in fragments:
            mol = Chem.MolFromSmiles(frag)
            if mol:
                for atom in mol.GetAtoms():
                    atom.SetAtomMapNum(0)
                clean_fragments.append(Chem.MolToSmiles(mol))
            else:
                clean_fragments.append(frag)
    except Exception:
        clean_fragments = fragments

    clean_fragments = [f for f in clean_fragments if f]
    if not clean_fragments:
        return "", []

    sorted_unique = sorted(set(clean_fragments))
    return ".".join(sorted_unique), sorted_unique


def fetch_reaction_conditions_unified(
    reaction_smiles: str,
    limit: int = 5,
    save_path: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], str]:
    
    output = (
        "# Reaction Conditions Search Results\n\n"
        f"## Query: `{reaction_smiles}`\n\n"
    )
    results = []
    reaction_smiles = str(reaction_smiles or "").strip()

    if not reaction_smiles:
        output += "⚠️ Error: reaction SMILES or input query cannot be empty.\n"
        save_json(results, save_path)
        return results, output

    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 5
    limit = max(1, min(limit, 100))

    if not os.path.isfile(ORD_DB_PATH):
        output += f"⚠️ ORD SQLite database not found: `{ORD_DB_PATH}`\n"
        save_json(results, save_path)
        return results, output

    parts = reaction_smiles.split(">", 2) if ">" in reaction_smiles else [reaction_smiles]
    raw_reactants = parts[0].strip() if len(parts) >= 1 else ""
    raw_products = parts[-1].strip() if len(parts) >= 2 else ""

    canon_reactants_key, reactant_frags, react_log = standardize_reaction_part(raw_reactants)
    canon_products_key, product_frags, prod_log = standardize_reaction_part(raw_products)

    if react_log or prod_log:
        output += "### Input Standardization Log:\n"
        if react_log:
            output += f"**Reactants Resolution:**\n{react_log}\n"
        if prod_log:
            output += f"**Products Resolution:**\n{prod_log}\n"
        output += "---\n\n"

    try:
        with closing(sqlite3.connect(ORD_DB_PATH, timeout=30)) as connection:
            connection.row_factory = sqlite3.Row
            cur = connection.cursor()
            rows = []

            main_reactant = max(reactant_frags, key=len) if reactant_frags else ""
            main_product = max(product_frags, key=len) if product_frags else ""
            
            all_frags = (product_frags or []) + (reactant_frags or [])
            main_comp = max(all_frags, key=len) if all_frags else ""

            if main_reactant:
                cur.execute(
                    """
                    SELECT DISTINCT rc.*
                    FROM reaction_conditions rc
                    JOIN reaction_components comp ON rc.reaction_id = comp.reaction_id
                    WHERE comp.smiles = ? AND comp.reaction_role IN ('REACTANT', 'REAGENT')
                    ORDER BY rc.yield_percent DESC NULLS LAST
                    LIMIT ?
                    """,
                    (main_reactant, limit)
                )
                rows = cur.fetchall()
                if rows:
                    output += f"*[Forward Prediction Match] Found records using core reactant (Index Match):* `{main_reactant}`\n\n"

            if not rows and main_product:
                cur.execute(
                    """
                    SELECT * FROM reaction_conditions
                    WHERE target_product_smiles = ?
                    ORDER BY yield_percent DESC NULLS LAST
                    LIMIT ?
                    """,
                    (main_product, limit)
                )
                rows = cur.fetchall()
                if rows:
                    output += f"*[Target Product Match] Found records producing target product (Index Match):* `{main_product}`\n\n"

            if not rows and main_comp:
                cur.execute(
                    """
                    SELECT DISTINCT rc.*
                    FROM reaction_conditions rc
                    JOIN reaction_components comp ON rc.reaction_id = comp.reaction_id
                    WHERE comp.smiles = ?
                    ORDER BY rc.yield_percent DESC NULLS LAST
                    LIMIT ?
                    """,
                    (main_comp, limit)
                )
                rows = cur.fetchall()
                if rows:
                    output += f"*[Component Match] Found records containing key molecule (Index Match):* `{main_comp}`\n\n"

            if not rows and main_comp:
                wildcard = f"%{main_comp}%"
                cur.execute(
                    """
                    SELECT * FROM reaction_conditions
                    WHERE reactants_smiles LIKE ? OR target_product_smiles LIKE ?
                    ORDER BY yield_percent DESC NULLS LAST
                    LIMIT ?
                    """,
                    (wildcard, wildcard, limit)
                )
                rows = cur.fetchall()
                if rows:
                    output += f"*[Fuzzy Fallback] Found related records via fuzzy string scan (Slow Match):* `{main_comp}`\n\n"

            if not rows:
                output += (
                    "⚠️ **Database Miss:** No empirical conditions were found for this specific core substrate in the local ORD database.\n\n"
                    "**🔥 INSTRUCTION TO AGENT (CRITICAL):**\n"
                    "Do NOT give up! You are a highly capable organic chemistry expert.\n"
                    "Please analyze the functional groups in the input.\n"
                    "Based on textbook organic chemistry, deduce the standard reaction mechanism and predict the most likely final product or reagents.\n"
                    "Output the inferred reaction type and the proposed product/reagents SMILES or SELFIES using your own internal knowledge."
                )
                save_json(results, save_path)
                return results, output

            output += f"### Found {len(rows)} matching records\n\n"

            temperatures, times, all_solvents, yields = [], [], [], []

            for number, row in enumerate(rows, start=1):
                solvents = parse_solvents(row["solvents"])
                
                temperature = float(row["temperature_celsius"]) if row["temperature_celsius"] is not None else None
                time_hours = float(row["time_hours"]) if row["time_hours"] is not None else None
                yield_pct = float(row["yield_percent"]) if row["yield_percent"] is not None else None
                
                target_smiles = row["target_product_smiles"]
                reactants_smiles = row["reactants_smiles"] if "reactants_smiles" in row.keys() else None
                reaction_smiles = row["reaction_smiles"] or "Not provided"

                target_selfies = None
                if target_smiles and SELFIES_AVAILABLE:
                    try:
                        target_selfies = sf.encoder(target_smiles)
                    except Exception as exc:
                        logger.debug("Failed to encode target product to SELFIES: %s", exc)

                cur.execute(
                    """
                    SELECT compound_name, smiles, reaction_role 
                    FROM reaction_components 
                    WHERE reaction_id = ? AND reaction_role IN ('REAGENT', 'CATALYST', 'SOLVENT')
                    """,
                    (row["reaction_id"],)
                )
                comp_rows = cur.fetchall()
                
                reagents_list = []
                for c in comp_rows:
                    identifier = c['compound_name'] or c['smiles']
                    if identifier:
                        reagents_list.append(f"{identifier} ({c['reaction_role']})")
                
                reagents_info = list(set(reagents_list))

                record = {
                    "reaction_id": row["reaction_id"],
                    "reaction_smiles": reaction_smiles,
                    "reactants_smiles": reactants_smiles,
                    "target_product_smiles": target_smiles,
                    "target_product_selfies": target_selfies,
                    "yield_percent": yield_pct,
                    "temperature_celsius": temperature,
                    "time_hours": time_hours,
                    "solvents": solvents,
                    "reagents": reagents_info,
                }
                results.append(record)

                output += (
                    f"**Record {number}**\n"
                    f"- **Reaction ID:** {row['reaction_id']}\n"
                    f"- **Full Reaction SMILES:** `{reaction_smiles}`\n"
                )

                if reactants_smiles:
                    output += f"- **Reactants SMILES:** `{reactants_smiles}`\n"

                if target_smiles:
                    output += f"- **Target Product SMILES:** `{target_smiles}`\n"
                    
                if target_selfies:
                    output += f"- **Target Product SELFIES:** `{target_selfies}`\n"

                if yield_pct is not None:
                    yields.append(yield_pct)
                    output += f"- **Yield:** {yield_pct:.1f}%\n"

                if temperature is not None:
                    temperatures.append(temperature)
                    output += f"- **Temperature:** {temperature:.1f} °C\n"

                if time_hours is not None:
                    times.append(time_hours)
                    output += f"- **Time:** {time_hours:.2f} hours\n"

                if solvents:
                    all_solvents.extend(solvents)
                    output += f"- **Solvents:** {', '.join(solvents)}\n"

                if reagents_info:
                    output += f"- **Reagents/Catalysts:** {', '.join(reagents_info)}\n"

                output += "\n"

    except (sqlite3.Error, OSError, RuntimeError) as exc:
        logger.exception("ORD query failed.")
        output += f"⚠️ **ORD database query failed:** {exc}\n"
        save_json(results, save_path)
        return results, output

    save_json(results, save_path)
    return results, output


# =====================================================================
# Regression tests
# =====================================================================

def run_regression_tests() -> None:
    require_rdkit()
    print("🚀 Running chemistry toolkit regression tests...")

    mol, smiles, log = standardize_to_rdkit_mol("Aspirin")
    assert mol is not None, log
    assert smiles
    assert mol_to_inchikey(mol) == "BSYNRYMUTXBXSQ-UHFFFAOYSA-N"

    mol, _, log = standardize_to_rdkit_mol(
        "[Na+]", parent_form=False, neutralize=False
    )
    assert mol is not None, log
    assert Chem.GetFormalCharge(mol) == 1

    mol, smiles, log = standardize_to_rdkit_mol(
        "C[C@@H](O)C(=O)O", parent_form=False, neutralize=False
    )
    assert mol is not None, log
    assert "@" in smiles

    mapped_product = (
        "CCO>>[CH3:1][C:2](=[O:3])[O:4][CH2:5][CH3:6]"
    )
    assert (
        canonical_reaction_product(mapped_product)
        == canonical_reaction_product(">>CC(=O)OCC")
    )

    assert extract_valid_cids({
        "IdentifierList": {"CID": [0, "0", None]}
    }) == []

    assert parse_chembl_phase(0.5)[0] == 0.5
    assert parse_chembl_phase(-1)[0] == -1.0
    assert parse_chembl_phase("invalid")[0] is None

    orbitals = analyze_mo_occupations(
        [-0.8, -0.4, 0.1, 0.4],
        [2.0, 2.0, 0.0, 0.0],
    )
    assert orbitals["homo_hartree"] == -0.4
    assert orbitals["lumo_hartree"] == 0.1

    print("✅ All local regression tests passed.")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    run_regression_tests()