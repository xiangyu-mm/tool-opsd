from typing import List, Dict, Any, Optional
import os
import requests
import time
import xml.etree.ElementTree as ET
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from xml.etree import ElementTree
import pandas as pd
import re

from .ratelimiter import RateLimiter

PUBMED_BASE_URL = "https://pubmed.ncbi.nlm.nih.gov/"
PUBMED_EU_UTILS_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
PUBMED_API_KEY = os.environ.get("PUBMED_API_KEY")
BATCH_REQUEST_SIZE = 100

__all__ = [
    "pubmed_api_get_paper_references",
    "get_pubmed_articles",
    "fetch_paper_content_by_pmid",
    "pubmed_api_search_papers", 
    "extract_relevant_sections", 
    "format_paper_content_output", 
]

# ===============================
# Helper functions
# ===============================
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
            if sentence_breaks:
                context_start = context_start + sentence_breaks[-1]

            post_context = text[end:context_end]
            sentence_breaks = [m.start() for m in re.finditer(r'[.!?]\s+', post_context)]
            if sentence_breaks:
                context_end = end + sentence_breaks[0] + 2

            context = text[context_start:context_end].strip()
            matches.append({
                'matched_text': match.group(0),
                'context': context,
                'start_pos': start,
                'end_pos': end
            })
    except re.error:
        search_term = grep_pattern.lower()
        text_lower = text.lower()
        start = 0
        while True:
            pos = text_lower.find(search_term, start)
            if pos == -1:
                break
            end = pos + len(search_term)
            context_start = max(0, pos - context_chars)
            context_end = min(len(text), end + context_chars)

            pre_context = text[context_start:pos]
            sentence_breaks = [m.end() for m in re.finditer(r'[.!?]\s+', pre_context)]
            if sentence_breaks:
                context_start = context_start + sentence_breaks[-1]

            post_context = text[end:context_end]
            sentence_breaks = [m.start() for m in re.finditer(r'[.!?]\s+', post_context)]
            if sentence_breaks:
                context_end = end + sentence_breaks[0] + 2

            matches.append({
                'matched_text': text[pos:end],
                'context': text[context_start:context_end].strip(),
                'start_pos': pos,
                'end_pos': end
            })
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
        if not is_duplicate:
            unique_matches.append(match)

    return unique_matches


def format_paper_content_output(result: Dict[str, Any], filter_keywords: str = "") -> str:
    output_parts = []
    if result.get('error'):
        output_parts.append(f"PMID: {result.get('pmid', 'Unknown')}")
        output_parts.append("=" * 80)
        output_parts.append(f"ERROR: {result['error']}")
        return "\n".join(output_parts)

    if result.get('executive_summary'):
        return result['executive_summary']

    output_parts.append(f"=== PMID: {result.get('pmid')} ===")
    output_parts.append(f"Title: {result.get('title', 'No title available')}")
    output_parts.append(f"Journal/Date: {result.get('journal', 'N/A')} ({result.get('pub_date', 'N/A')})")
    
    if result.get('mesh_terms'):
        output_parts.append(f"MeSH Keywords: {', '.join(result['mesh_terms'][:8])}")
        
    output_parts.append(f"\n--- ABSTRACT ---\n{result.get('abstract', 'No abstract available')}")

    has_full = result.get('has_full_text', False)
    source = result.get('source', 'none')
    source_name = {'pmc': 'PMC Open Access', 'pubtator': 'PubTator3', 'none': 'None'}.get(source, source)
    
    output_parts.append(f"\nFULL TEXT AVAILABLE: {'Yes' if has_full else 'No'} (Source: {source_name})")

    relevant_passages = result.get('relevant_passages', [])
    if relevant_passages:
        output_parts.append("\n--- RELEVANT EXTRACTS ---")
        for idx, item in enumerate(relevant_passages, 1):
            kws = ", ".join(item.get("matched_keywords", []))
            output_parts.append(f"[{idx}] Zone ({item.get('section')}) | Matches: [{kws}]\n{item.get('text')}\n")
    elif filter_keywords and has_full:
        output_parts.append(f"\nNOTE: Full text searched, but no specific passages matched keywords: '{filter_keywords}'.")

    return "\n".join(output_parts)


def _parse_and_extract_citation_relations(xml_response: str, relation_type: str) -> List[Dict[str, Any]]:
    results = []
    try:
        root = ET.fromstring(xml_response)
        for linkset in root.findall(".//LinkSet"):
            source_pmid_elem = linkset.find(".//IdList/Id")
            if source_pmid_elem is None:
                continue
            source_pmid = source_pmid_elem.text
            
            linkname_map = {'cited_by': 'pubmed_pubmed_citedin', 'cites': 'pubmed_pubmed_refs'}
            target_linkname = linkname_map.get(relation_type)
            
            for linksetdb in linkset.findall(".//LinkSetDb"):
                linkname_elem = linksetdb.find("LinkName")
                if linkname_elem is not None and linkname_elem.text == target_linkname:
                    for link_elem in linksetdb.findall(".//Link/Id"):
                        target_pmid = link_elem.text
                        results.append({
                            'source_pmid': source_pmid,
                            'target_pmid': target_pmid,
                            'relation_type': relation_type
                        })
    except ET.ParseError as e:
        print(f"Error parsing XML: {e}")
    return results

def _get_cites_relations_one_request(pmids: List[str], rate_limiter: RateLimiter = None) -> List[Dict[str, Any]]:
    if not pmids:
        return []

    if rate_limiter is not None:
        rate_limiter.wait_if_needed()
    
    id_params = "&".join([f"id={pmid}" for pmid in pmids])
    url = f"{PUBMED_EU_UTILS_BASE_URL}/elink.fcgi?dbfrom=pubmed&linkname=pubmed_pubmed_refs&{id_params}"
    if PUBMED_API_KEY:
        url = f"{url}&api_key={PUBMED_API_KEY}"
    
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return _parse_and_extract_citation_relations(response.text, 'cites')
    except requests.RequestException as e:
        print(f"Error fetching cites relations: {e}")
        return []

def _get_cites_relations_batch_worker(pmid_batch: List[str], rate_limiter: RateLimiter, batch_id: int) -> Dict[str, Any]:
    try:
        results = _get_cites_relations_one_request(pmid_batch, rate_limiter)
        return {'batch_id': batch_id, 'pmid_batch': pmid_batch, 'results': results, 'success': True}
    except Exception as e:
        return {'batch_id': batch_id, 'pmid_batch': pmid_batch, 'results': [], 'success': False, 'error': str(e)}

# ---------------------------------------------------------
# Robust XML Parsing replacing the brittle _parse_xml_recursively
# ---------------------------------------------------------
def _parse_article_xml_to_dict(article: ET.Element) -> Optional[Dict[str, Any]]:
    """Safely extract fields from PubmedArticle using itertext() to handle nested tags."""
    try:
        results = {}
        # PMID
        pmid_elem = article.find('.//PMID')
        if pmid_elem is None:
            return None
        results['PMID'] = pmid_elem.text.strip() if pmid_elem.text else ""

        # Journal
        journal_elem = article.find('.//Journal/Title')
        results['Journal'] = "".join(journal_elem.itertext()).strip() if journal_elem is not None else ""

        # Title
        title_elem = article.find('.//ArticleTitle')
        results['Title'] = "".join(title_elem.itertext()).strip() if title_elem is not None else ""

        # Date
        year = article.find('.//PubDate/Year')
        medline_date = article.find('.//PubDate/MedlineDate')
        month = article.find('.//PubDate/Month')
        day = article.find('.//PubDate/Day')
        
        results['Year'] = year.text.strip() if year is not None and year.text else (medline_date.text.strip() if medline_date is not None and medline_date.text else "")
        results['Month'] = month.text.strip() if month is not None and month.text else ""
        results['Day'] = day.text.strip() if day is not None and day.text else ""

        # Authors
        authors = []
        for author in article.findall('.//AuthorList/Author'):
            ln = author.find('LastName')
            fn = author.find('ForeName')
            ln_str = ln.text.strip() if ln is not None and ln.text else ""
            fn_str = fn.text.strip() if fn is not None and fn.text else ""
            if fn_str or ln_str:
                authors.append(f"{fn_str} {ln_str}".strip())
        results['Authors'] = ", ".join(authors)

        # PubType
        pub_types = []
        for pt in article.findall('.//PublicationTypeList/PublicationType'):
            if pt.text:
                pub_types.append(pt.text.strip())
        results['Publication Type'] = ", ".join(pub_types)

        # Abstract
        abstract_parts = []
        for abs_text in article.findall('.//Abstract/AbstractText'):
            label = abs_text.get('Label', '')
            text = "".join(abs_text.itertext()).strip()
            if label and text:
                abstract_parts.append(f"{label}: {text}")
            elif text:
                abstract_parts.append(text)
        results['Abstract'] = "\n".join(abstract_parts)
        
        return results
    except Exception as e:
        print(f"Warning: Failed to parse an article: {e}")
        return None

def _parse_book_xml_to_dict(book: ET.Element) -> Optional[Dict[str, Any]]:
    """Safely extract fields from PubmedBookArticle."""
    try:
        results = {}
        pmid_elem = book.find('.//PMID')
        if pmid_elem is None:
            return None
        results['PMID'] = pmid_elem.text.strip() if pmid_elem.text else ""

        title_elem = book.find('.//BookTitle')
        results['Title'] = "".join(title_elem.itertext()).strip() if title_elem is not None else ""

        year = book.find('.//PubDate/Year')
        month = book.find('.//PubDate/Month')
        day = book.find('.//PubDate/Day')
        results['Year'] = year.text.strip() if year is not None and year.text else ""
        results['Month'] = month.text.strip() if month is not None and month.text else ""
        results['Day'] = day.text.strip() if day is not None and day.text else ""

        authors = []
        for author in book.findall('.//AuthorList/Author'):
            ln = author.find('LastName')
            fn = author.find('ForeName')
            ln_str = ln.text.strip() if ln is not None and ln.text else ""
            fn_str = fn.text.strip() if fn is not None and fn.text else ""
            if fn_str or ln_str:
                authors.append(f"{fn_str} {ln_str}".strip())
        results['Authors'] = ", ".join(authors)
        
        pub_type = book.find('.//PublicationType')
        results['Publication Type'] = pub_type.text.strip() if pub_type is not None and pub_type.text else ""

        abstract_parts = []
        for abs_text in book.findall('.//Abstract/AbstractText'):
            text = "".join(abs_text.itertext()).strip()
            if text:
                abstract_parts.append(text)
        results['Abstract'] = "\n".join(abstract_parts)
        
        return results
    except Exception as e:
        print(f"Warning: Failed to parse a book: {e}")
        return None

def _retrieve_abstract_from_efetch(pmids: List[str], api_key: str = None) -> pd.DataFrame:
    """Retrieve the abstract from the efetch API robustly."""
    all_abstracts = []
    url = f"{PUBMED_EU_UTILS_BASE_URL}/efetch.fcgi"
    
    for i in range(0, len(pmids), BATCH_REQUEST_SIZE):
        pmid_subset = pmids[i:i+BATCH_REQUEST_SIZE]
        params = {
            "db": "pubmed",
            "id": ",".join(pmid_subset),
            "retmode": "xml"
        }
        if api_key:
            params["api_key"] = api_key
            
        try:
            # POST is safer for large parameter payloads in eUtils
            response = requests.post(url, data=params, timeout=30)
            if response.status_code != 200:
                continue
                
            tree = ET.fromstring(response.content)
            
            # Extract standard articles
            for article in tree.findall(".//PubmedArticle"):
                parsed = _parse_article_xml_to_dict(article)
                if parsed:
                    all_abstracts.append(parsed)
                    
            # Extract books
            for book in tree.findall(".//PubmedBookArticle"):
                parsed = _parse_book_xml_to_dict(book)
                if parsed:
                    all_abstracts.append(parsed)
                    
        except requests.RequestException as e:
            print(f"Network error in efetch: {e}")
            continue
        except ET.ParseError as e:
            print(f"XML parsing error in efetch: {e}")
            continue

    if all_abstracts:
        return pd.DataFrame.from_records(all_abstracts)
    else:
        return pd.DataFrame()


# ===============================
# Main functions
# ===============================
def pubmed_api_get_paper_references(
    pmids: List[str],
    batch_size: int = 100,
    mini_batch_size: int = 20,
    max_workers: int = 4,
    rate_limit: float = 3.0
) -> List[Dict[str, Any]]:
    all_results = []
    if not pmids:
        return all_results

    rate_limiter = RateLimiter(max_requests_per_second=rate_limit)
    for i in tqdm(range(0, len(pmids), batch_size), desc="Processing citation batches"):
        end_idx = min(i + batch_size, len(pmids))
        main_batch_pmids = pmids[i:end_idx]
        
        mini_batches = [main_batch_pmids[j:min(j + mini_batch_size, len(main_batch_pmids))] 
                        for j in range(0, len(main_batch_pmids), mini_batch_size)]
        
        try:
            batch_results = []
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_batch = {
                    executor.submit(_get_cites_relations_batch_worker, mb, rate_limiter, idx): idx
                    for idx, mb in enumerate(mini_batches)
                }
                
                for future in as_completed(future_to_batch):
                    try:
                        result = future.result()
                        if result['success']:
                            batch_results.extend(result['results'])
                    except Exception as e:
                        pass
            
            pmid_grouped_results = {}
            for relation in batch_results:
                pmid_grouped_results.setdefault(relation['source_pmid'], []).append(relation)
            
            for pmid in main_batch_pmids:
                all_results.extend(pmid_grouped_results.get(pmid, []))
            
        except Exception as e:
            continue
            
    if len(all_results) > 0:
        df_results = pd.DataFrame(all_results)
        target_pmids = df_results['target_pmid'].unique().tolist()
        target_content = _retrieve_abstract_from_efetch(target_pmids, PUBMED_API_KEY)
        
        if not target_content.empty:
            target_content = target_content[['PMID', 'Title', 'Year']]
            target_content.columns = ['target_pmid', 'target_title', 'target_year']
            df_results = pd.merge(df_results, target_content, on='target_pmid', how='left')
        
        # Convert back to list of dicts to maintain old signature if expected, 
        # but your original code returned pd.DataFrame at this step. 
        # Kept as DataFrame per your original implementation ending.
        return df_results
    return all_results

def get_pubmed_articles(term: str) -> str:
    base_url_pubmed = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    search_url = f"{base_url_pubmed}/esearch.fcgi"
    fetch_url = f"{base_url_pubmed}/efetch.fcgi"
    
    # Use params dictionary for automatic URL encoding!
    search_params = {
        "db": "pubmed",
        "term": term,
        "retmode": "xml",
        "retmax": "5",
        "sort": "relevance"
    }
    
    try:
        search_response = requests.get(search_url, params=search_params, timeout=20)
        search_results = ElementTree.fromstring(search_response.content)
        id_list = [id_tag.text for id_tag in search_results.findall('.//Id')]
    except Exception as e:
        return f"Error parsing search results: {e}"
    
    if not id_list:
        return "No articles found for the query."
    
    fetch_params = {
        "db": "pubmed",
        "id": ",".join(id_list),
        "retmode": "xml"
    }
    
    try:
        fetch_response = requests.get(fetch_url, params=fetch_params, timeout=20)
        articles = ElementTree.fromstring(fetch_response.content)
    except Exception as e:
        return f"Error parsing fetch results: {e}"

    results = [] 
    for article in articles.findall('.//PubmedArticle'):
        pmid_elem = article.find('.//PMID')
        pmid = pmid_elem.text if pmid_elem is not None else "No PMID available"
        
        # Safe title/abstract extraction
        title_elem = article.find('.//ArticleTitle')
        title = "".join(title_elem.itertext()).strip() if title_elem is not None else "No title available"
        
        abstract_parts = []
        for abs_text in article.findall('.//Abstract/AbstractText'):
            abstract_parts.append("".join(abs_text.itertext()).strip())
        abstract_text = " ".join(abstract_parts) if abstract_parts else "No abstract available"
        
        results.append(f"PMID: {pmid}\nTitle: {title}\nAbstract: {abstract_text}\n")
    return "".join(results)


get_pubmed_articles_doc = {
    "name": "get_pubmed_articles",
    "description": "Given a PubMed query, return related PubMed articles containing titles and abstractions.",
    "parameters": {
        "type": "object",
        "properties": {
            "term": {
                "type": "string",
                "description": "a search query or pubmed ID.",
            },
        },
        "required": ["term"],
    },
}


def fetch_paper_content_by_pmid(
    pmid: str, 
    filter_keywords: Optional[List[str]] = None,
    max_relevant_count: int = 5,
    single_passage_length: int = 800,
    total_budget_max_len: int = 3500
) -> Dict[str, Any]:
    
    result = {
        "pmid": pmid,
        "title": None,
        "journal": None,
        "pub_date": None,
        "abstract": None,
        "mesh_terms": [],
        "keywords": [],
        "has_full_text": False,
        "sections": {},          
        "relevant_passages": [], 
        "executive_summary": "",
        "source": "none",
        "error": None
    }
    
    base_url_pubmed = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    try:
        fetch_params = {
            "db": "pubmed",
            "id": pmid,
            "retmode": "xml"
        }
        if PUBMED_API_KEY:
            fetch_params["api_key"] = PUBMED_API_KEY
            
        response = requests.get(base_url_pubmed, params=fetch_params, timeout=20)
        response.raise_for_status()
        
        root = ElementTree.fromstring(response.content)
        article = root.find('.//PubmedArticle')
        
        if article is not None:
            title_elem = article.find('.//ArticleTitle')
            result["title"] = "".join(title_elem.itertext()).strip() if title_elem is not None else "No title available"
            
            journal_elem = article.find('.//Journal/Title')
            result["journal"] = "".join(journal_elem.itertext()).strip() if journal_elem is not None else None
            
            pub_date_year = article.find('.//JournalIssue/PubDate/Year')
            result["pub_date"] = pub_date_year.text.strip() if pub_date_year is not None and pub_date_year.text else None

            abstract_parts = []
            for abs_text in article.findall('.//Abstract/AbstractText'):
                label = abs_text.get('Label', '')
                text = "".join(abs_text.itertext()).strip()
                if label and text:
                    abstract_parts.append(f"[{label}]: {text}")
                elif text:
                    abstract_parts.append(text)
            result["abstract"] = "\n".join(abstract_parts) if abstract_parts else "No abstract available"
            
            mesh_terms = [
                m.find('DescriptorName').text.strip() 
                for m in article.findall('.//MeshHeading') 
                if m.find('DescriptorName') is not None and m.find('DescriptorName').text
            ]
            keywords = [k.text.strip() for k in article.findall('.//Keyword') if k.text]
            result["mesh_terms"] = mesh_terms
            result["keywords"] = keywords
            
        else:
            result["error"] = f"PMID {pmid} not found in PubMed."
            return result
            
    except Exception as e:
        result["error"] = f"PubMed Fetch Error: {str(e)}"
        return result

    raw_passages = []
    try:
        pmc_url = f"https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/pmcoa.cgi/BioC_json/{pmid}/unicode"
        pmc_resp = requests.get(pmc_url, timeout=25)
        
        if pmc_resp.status_code == 200:
            pmc_data = pmc_resp.json()
            if isinstance(pmc_data, list) and len(pmc_data) > 0:
                docs = pmc_data[0].get('documents', [])
                if docs:
                    raw_passages = docs[0].get('passages', [])
                    result["source"] = "pmc"
                    result["has_full_text"] = True
    except Exception:
        pass 

    if not raw_passages:
        try:
            pubtator_url = f"https://www.ncbi.nlm.nih.gov/research/pubtator3-api/publications/export/biocjson?pmids={pmid}"
            pub_resp = requests.get(pubtator_url, timeout=20)
            if pub_resp.status_code == 200:
                pub_data = pub_resp.json().get('PubTator3', [])
                if pub_data:
                    raw_passages = pub_data[0].get('passages', [])
                    has_body = any(
                        p.get('infons', {}).get('type', '').lower() not in ['title', 'abstract', 'front'] 
                        for p in raw_passages
                    )
                    if has_body:
                        result["source"] = "pubtator"
                        result["has_full_text"] = True
        except Exception:
            pass

    sections: Dict[str, List[str]] = {}
    relevant_passages = []
    seen_texts = set()  

    keywords_lower = [k.lower().strip() for k in filter_keywords if k.strip()] if filter_keywords else []

    for passage in raw_passages:
        infons = passage.get('infons', {})
        sec_type = infons.get('section_type') or infons.get('type') or 'OTHER'
        sec_type = sec_type.upper().strip()
        
        if sec_type in ['TITLE', 'ABSTRACT', 'FRONT', 'ABSTRACT_TITLE_1']:
            continue
            
        text = passage.get('text', '').strip()
        if not text or text in seen_texts:
            continue
            
        seen_texts.add(text)
        
        if sec_type not in sections:
            sections[sec_type] = []
        sections[sec_type].append(text)
        
        if keywords_lower and len(relevant_passages) < max_relevant_count:
            text_lower = text.lower()
            matched_kws = [kw for kw in keywords_lower if kw in text_lower]
            if matched_kws:
                snippet = text[:single_passage_length] + "..." if len(text) > single_passage_length else text
                relevant_passages.append({
                    "section": sec_type,
                    "matched_keywords": matched_kws,
                    "text": snippet
                })

    result["sections"] = {sec: "\n\n".join(texts) for sec, texts in sections.items()}
    result["relevant_passages"] = relevant_passages

    mesh_str = ", ".join(result["mesh_terms"][:8]) if result["mesh_terms"] else "None listed"
    summary_parts = [
        f"=== PMID: {pmid} ===",
        f"Title: {result['title']}",
        f"Journal/Date: {result['journal'] or 'N/A'} ({result['pub_date'] or 'N/A'})",
        f"MeSH Keywords: {mesh_str}",
        f"\n--- ABSTRACT ---\n{result['abstract']}"
    ]
    
    if result["relevant_passages"]:
        summary_parts.append("\n[FULL TEXT STATUS]: Open-access full text AVAILABLE and target keywords matched.")
        summary_parts.append("\n--- RELEVANT EXTRACTS (Matching Target Keywords) ---")
        for idx, item in enumerate(result["relevant_passages"], 1):
            kws = ", ".join(item["matched_keywords"])
            summary_parts.append(f"[{idx}] Zone ({item['section']}) | Matches: [{kws}]\n{item['text']}")
            
    elif result["has_full_text"]:
        summary_parts.append(
            "\n[FULL TEXT STATUS]: Open-access full text is AVAILABLE, but no passages matched the provided keywords. "
            "Displaying key section preview below."
        )
        key_previews = []
        for target_sec in ["RESULTS", "CONCLUSION", "DISCUSS"]:
            matched_sec_keys = [k for k in result["sections"].keys() if target_sec in k]
            if matched_sec_keys:
                sec_name = matched_sec_keys[0]
                sec_text = result["sections"][sec_name]
                preview = sec_text[:single_passage_length] + "..." if len(sec_text) > single_passage_length else sec_text
                key_previews.append(f"[{sec_name}]\n{preview}")
                break
                
        if key_previews:
            summary_parts.append("\n--- KEY SECTION PREVIEW ---")
            summary_parts.extend(key_previews)
            
    else:
        summary_parts.append(
            "\n[FULL TEXT STATUS]: Open-access full text is NOT available on PMC/PubTator for this PMID. "
            "Analysis must rely solely on the Abstract above, or search for alternative PMIDs with full-text availability."
        )

    full_summary = "\n\n".join(summary_parts)
    if len(full_summary) > total_budget_max_len:
        full_summary = full_summary[:total_budget_max_len] + "\n\n...[Remainder Truncated to Maintain LLM Context Budget]"
        
    result["executive_summary"] = full_summary
    return result


def pubmed_api_search_papers(
    boolean_query_text: str,
    top_k: int = 10,
) -> Optional[pd.DataFrame]:
    """
    Search for papers using PubMed API.
    
    Args:
        boolean_query_text: Boolean query text for PubMed search.
        top_k: Maximum number of results to return.
    
    Returns:
        Optional[pd.DataFrame]: DataFrame containing search results.
    """    
    search_url = f"{PUBMED_EU_UTILS_BASE_URL}/esearch.fcgi"
    
    # [FIX] Replace string concatenation with requests params 
    # to automatically URL-encode spaces and special characters.
    # [FIX] Added 'sort': 'relevance' so top_k returns the best matches, not random/old ones.
    params = {
        "db": "pubmed",
        "term": boolean_query_text,
        "retmax": top_k,
        "retmode": "json",
        "sort": "relevance"
    }
    
    if PUBMED_API_KEY:
        params["api_key"] = PUBMED_API_KEY
        
    try:
        response = requests.get(search_url, params=params, timeout=30)
        response.raise_for_status()
        response_dict = response.json()
        pmid_list = response_dict.get('esearchresult', {}).get('idlist', [])
    except requests.RequestException as e:
        print(f"Error searching papers: {e}")
        return None
    
    if not pmid_list:
        return None
    
    # get the paper details for pmids
    paper_details = _retrieve_abstract_from_efetch(pmid_list, PUBMED_API_KEY)
    
    if paper_details is None or paper_details.empty:
        return None

    # returns DataFrame: PMID, Title, Year, Journal, Authors, Abstract, etc.
    return paper_details