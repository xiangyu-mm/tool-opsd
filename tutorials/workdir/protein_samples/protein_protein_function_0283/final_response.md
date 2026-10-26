1. [✓] Analyze sequence composition, length, and conserved motifs  
2. [✓] Search curated protein homologs and functional annotations  
3. [✓] Record findings in the knowledge graph  
4. [✓] Review the stored evidence  
5. [✓] Provide a concise, evidence-qualified functional summary  

## Functional identification

The 184-amino-acid sequence is an **exact sequence match** to the reviewed *Dictyostelium discoideum* protein **Ras-related protein RabN2** (**UniProt Q54FK2**). The match has 100% sequence identity and complete coverage, providing strong evidence for the protein’s identity and function.

### Protein family and molecular function

RabN2 belongs to the **Ras-like small GTPase** family. Its predicted functions are:

- **GTP binding**
- **GTP hydrolysis**
- Acting as a nucleotide-dependent molecular switch
- Regulating intracellular membrane-trafficking events

The overall reaction is:

\[
\mathrm{GTP + H_2O \rightarrow GDP + phosphate + H^+}
\]

The sequence contains a strongly supported **Ras domain** spanning approximately residues 1–172. Pfam also identifies a **Roc-like domain** region near the N-terminus, although the functional interpretation of that secondary domain assignment should be treated more cautiously than the exact curated RabN2 match.

Rab proteins generally cycle between:

- an active, GTP-bound state, and
- an inactive, GDP-bound state.

This cycle allows them to recruit or release trafficking factors, including tethering proteins, motor-associated factors, and membrane-fusion machinery.

## Subcellular localization

The curated annotation for Q54FK2 places RabN2 in:

- **Late endosomes**
- **Lysosomes**
- **Phagocytic vesicles**

Thus, it is most likely an intracellular regulator of the **endolysosomal and phagocytic vesicle system**.

The sequence does not contain an obvious N-terminal signal peptide or transmembrane helix, consistent with Rab proteins being soluble peripheral membrane proteins rather than integral membrane proteins. However, the submitted sequence ends in `KIK` and does not show a canonical C-terminal cysteine-based prenylation motif. Therefore, although the curated protein is associated with vesicular compartments, the exact membrane-attachment mechanism cannot be established from this sequence alone.

## Biological processes

The strongest curated biological-process annotation is:

- **Phagosome–lysosome fusion** — GO:0090385

This suggests that RabN2 helps coordinate the maturation of phagosomes and their fusion with lysosomes. Such a role would support:

1. Delivery of lysosomal hydrolases to phagosomes  
2. Degradation of engulfed particles or cellular material  
3. Maturation of phagocytic compartments  
4. Endolysosomal membrane trafficking and vesicle fusion  

Related RabN proteins in *Dictyostelium* are also associated with late endosomes, lysosomes, phagocytic vesicles, and plasma-membrane-related trafficking processes. Those related annotations support a vesicle-trafficking role but should not be interpreted as direct experimental evidence for every function of RabN2.

## Sequence properties

- **Length:** 184 amino acids  
- **Predicted molecular mass:** approximately 21.3 kDa  
- **Theoretical pI:** 5.82  
- **Calculated charge at pH 7:** approximately −3.2  
- **GRAVY score:** −0.36, consistent with a moderately hydrophilic soluble protein  
- **Ras domain:** approximately residues 1–172  
- **Roc-like domain prediction:** approximately residues 1–99  

## Evidence strength and limitations

The functional assignment is unusually strong because the sequence exactly matches a reviewed UniProt/Swiss-Prot entry. The following annotations are therefore well supported:

- Rab-family small GTPase identity  
- GTP binding and GTPase activity  
- Localization to late endosomal, lysosomal, and phagocytic compartments  
- Participation in phagosome–lysosome fusion  

The available evidence does **not** establish:

- Specific interacting partners  
- Exact nucleotide-exchange or GTPase-activating proteins  
- Membrane anchoring chemistry  
- Oligomeric state  
- Tissue- or condition-specific regulation  
- Detailed substrate or vesicle specificity beyond the curated annotations  

## Concise functional summary

This protein is **RabN2, a small Ras-like GTPase from *Dictyostelium discoideum***. It likely functions as a molecular switch controlling endolysosomal and phagocytic membrane trafficking. Its principal annotated role is promoting or regulating **phagosome–lysosome fusion**, thereby contributing to phagosome maturation and degradation of engulfed material. It is associated with late endosomes, lysosomes, and phagocytic vesicles, although the precise mechanism of membrane attachment is not clear from the sequence alone.