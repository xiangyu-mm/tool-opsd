## Protein summary

1. [✓] Sequence properties and homology evaluated  
2. [✓] Functional, catalytic, cofactor, pathway, and domain evidence reviewed  
3. [✓] Findings recorded and cross-checked in the evidence graph  
4. [✓] Final functional summary prepared  

### Overall identification

The 428-residue protein is a **bacterial kynureninase**, a **pyridoxal 5′-phosphate (PLP)-dependent enzyme**.

This assignment is exceptionally strong: the sequence is an **exact sequence match** to reviewed UniProt entry **A4IT57** from *Geobacillus thermodenitrificans*.

### Core function

Kynureninase cleaves kynurenine substrates:

- **L-kynurenine + H₂O → anthranilate + L-alanine**
- **3-hydroxy-L-kynurenine + H₂O → 3-hydroxyanthranilate + L-alanine**

The enzyme is classified as:

- **EC 3.7.1.3**
- Rhea reactions: **RHEA:16813** and **RHEA:25143**

### Cofactor and catalytic features

- **Cofactor:** pyridoxal 5′-phosphate, PLP  
- **PLP-binding lysine:** residue **Lys239** in the matched reference annotation  
- Additional conserved/reference binding-site residues occur around positions **104–105, 132–135, 213, 216, 238, 267, and 295**.
- The PLP linkage is expected to form through the conserved catalytic lysine, as typical for PLP-dependent kynureninases.

### Domains

Detected Pfam domains:

| Domain | Accession | Approximate position | Interpretation |
|---|---:|---:|---|
| Aminotran_5 | PF00266 | 85–376 | Main aminotransferase-like catalytic fold |
| KYNU_C | PF22580 | 319–408 | C-terminal kynureninase-associated region |

The domain architecture is consistent with the kynureninase assignment rather than a generic aminotransferase annotation.

### Physical and predicted properties

- **Length:** 428 amino acids  
- **Estimated molecular mass:** 48.33 kDa  
- **Theoretical pI:** 5.89  
- **Estimated charge at pH 7:** −8.25  
- **GRAVY:** −0.193, indicating an overall slightly hydrophilic character  
- **Aromaticity:** 0.105  
- **Instability index:** 46.3; this computational score is slightly above the conventional stability cutoff and should not be treated as an experimental stability measurement.

The sequence lacks an obvious long hydrophobic segment, consistent with a soluble enzyme, although topology prediction was not performed.

### Cellular and oligomeric state

Curated reference annotations indicate:

- **Localization:** cytoplasm  
- **Oligomeric state:** homodimer  

### Biological pathways

The protein participates in:

1. **Kynurenine degradation**, producing anthranilate and alanine.
2. **NAD⁺ biosynthesis**, contributing to the pathway from kynurenine toward quinolinate.

Relevant Gene Ontology annotations include:

- **GO:0030429 — kynureninase activity**
- **GO:0030170 — pyridoxal phosphate binding**
- **GO:0005737 — cytoplasm**
- **GO:0006569 — L-tryptophan catabolic process**
- **GO:0009435 — NAD⁺ biosynthetic process**
- **GO:0019805 — quinolinate biosynthetic process**

### Bottom line

This is a **~48 kDa cytosolic, homodimeric, PLP-dependent kynureninase**. It cleaves L-kynurenine and 3-hydroxy-L-kynurenine to generate anthranilate or 3-hydroxyanthranilate plus alanine, linking tryptophan/kynurenine catabolism with bacterial NAD⁺ biosynthesis. The annotation is supported by an exact reviewed-protein sequence match, conserved PLP-binding features, and matching Aminotran_5/KYNU_C domains.