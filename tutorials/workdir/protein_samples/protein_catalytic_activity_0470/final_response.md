## Functional identification

This 768-residue protein is most consistent with **RAG1 (V(D)J recombination-activating protein 1)**, likely a compact/core RAG1 homolog.

The identification is strongly supported by:

- High similarity to reviewed vertebrate RAG1 proteins:
  - 67.2% identity to trout RAG1 over 99% of the query
  - 64.9% identity to zebrafish RAG1 over 99% of the query
  - 48.8% identity to chicken RAG1 over 98% of the query
- RAG1-specific domain architecture:
  - RAG1 impurity-binding region: residues 13–310
  - C3HC4/RING-like zinc-finger region: approximately 312–350
  - RAG1 DNA-binding region: approximately 418–548
  - Pre-RNase-H and RNase-H-like catalytic regions: approximately 549–757
- Basic character consistent with nucleic-acid binding:
  - predicted molecular mass: ~85.8 kDa
  - theoretical pI: 8.72

## Main catalytic activity: DNA cleavage during V(D)J recombination

RAG1 is the catalytic subunit of the **RAG1–RAG2 recombinase complex**. It binds recombination signal sequences (RSSs) adjacent to antigen-receptor gene segments and catalyzes site-specific DNA cleavage.

The reaction occurs in two chemical stages:

1. **Single-strand nicking**

\[
\text{DNA phosphodiester bond} + H_2O
\rightarrow
\text{DNA }3'\text{-OH} + \text{DNA }5'\text{-phosphate}
\]

2. **Hairpin formation by transesterification**

The newly generated 3′-OH attacks the phosphodiester bond on the opposite DNA strand:

\[
\text{DNA }3'\text{-OH} + \text{opposite-strand phosphodiester bond}
\rightarrow
\text{hairpin coding end} + \text{blunt signal end}
\]

The products are therefore:

- two sealed, hairpin-ended coding ends
- two blunt signal ends with 5′-phosphates

This cleavage initiates rearrangement of immunoglobulin and T-cell-receptor gene segments. The reaction requires **RAG2** and is supported by divalent metal ions, principally **Mg²⁺ or Mn²⁺**.

## Additional enzymatic activity

RAG1 is also annotated as an **E3 ubiquitin-protein ligase**. In this activity, it facilitates ubiquitin transfer from an E2 ubiquitin-conjugating enzyme to a lysine residue on an acceptor protein:

\[
\text{E2–ubiquitin} + \text{substrate-Lys}
\rightarrow
\text{E2} + \text{substrate-Lys–ubiquitin}
\]

One reported biological context is monoubiquitination of histone H3 during V(D)J recombination. This activity is secondary to the defining RAG1 DNA-cleavage function.

## Functional summary

**Predicted function:** RAG1-like, sequence-specific DNA endonuclease and E3 ubiquitin ligase.

**Primary reaction:** Metal-dependent cleavage of DNA at recombination signal sequences through nicking followed by 3′-OH-mediated transesterification, producing hairpin coding ends and blunt signal ends.

**Biological role:** Initiation of V(D)J recombination and assembly of antigen-receptor genes.

The functional assignment is strongly supported by homology and domain architecture, although the evidence for this exact sequence is computational and annotation-transfer based rather than a direct biochemical assay of the submitted protein.