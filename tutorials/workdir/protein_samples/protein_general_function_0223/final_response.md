1. [✓] Calculate sequence properties and inspect composition  
2. [✓] Compare against annotated protein homologs and retrieve functional annotations  
3. [✓] Review evidence for domains, catalytic activity, cofactors, localization, and pathways  
4. [✓] Prepare a concise functional summary with uncertainty noted  

## Functional summary

This 397-residue protein is most confidently identified as an **NADH-dependent enoyl-[acyl-carrier-protein] reductase** involved in bacterial **type II fatty-acid biosynthesis (FAS II)**.

It is an exact sequence match to the reviewed UniProt protein **Q1H0P3**, annotated as an enoyl-ACP reductase from *Methylobacillus flagellatus*. Additional homologs show approximately **77% sequence identity across the full length**, supporting the assignment strongly.

### Likely reaction

The enzyme catalyzes the final reduction step of each FAS II elongation cycle:

\[
\text{trans-2-enoyl-ACP} + \text{NADH} + H^+
\rightarrow \text{acyl-ACP} + \text{NAD}^+
\]

The substrate is an enoyl group linked to **acyl carrier protein (ACP)**. Related annotations also report activity toward enoyl-CoA, but the primary and best-supported role is enoyl-ACP reduction.

### Key characteristics

- **Length:** 397 amino acids  
- **Estimated molecular mass:** 43.44 kDa  
- **Theoretical pI:** 5.43  
- **Predicted charge at pH 7:** approximately −8.9  
- **Subunit:** Annotated as a monomer  
- **Cofactor:** NADH; the reference annotation specifically supports NADH rather than NADPH  
- **EC number:** **EC 1.3.1.9**  
- **Rhea reaction:** **RHEA:10240**  
- **Biological pathway:** Fatty-acid biosynthesis, FAS II  
- **Likely cellular context:** A soluble bacterial metabolic enzyme; the sequence has no obvious signal peptide or transmembrane segment.

### Domain organization

Pfam analysis identifies three conserved regions:

- **Eno-Rase_NADH_b (PF12242):** residues 2–78  
- **Enoyl_reductase (PF12241):** residues 81–316  
- **Eno-Rase_FAD_bd (PF07055):** residues 322–385  

The presence of the enoyl-reductase domain architecture strongly supports the functional assignment. The FAD-binding-family annotation should not by itself be interpreted as proof that FAD is the catalytic cofactor; the curated homolog annotation identifies **NADH** as the relevant reductant.

### Catalytic and functional features

In the exact reviewed reference protein:

- A conserved **proton-donor active-site residue** occurs at approximately position **234**.
- A site around position **74** contributes to discrimination between **NADH and NADPH**.
- GO annotations include:
  - **GO:0004318:** enoyl-[acyl-carrier-protein] reductase activity  
  - **GO:0051287:** NAD binding  
  - **GO:0006633:** fatty-acid biosynthetic process  

## Bottom line

The sequence encodes a **bacterial NADH-dependent enoyl-ACP reductase of the FAS II pathway**, responsible for reducing double bonds in fatty-acid intermediates during chain elongation. Because the sequence is an exact match to a reviewed Swiss-Prot entry, this assignment is high confidence. Exact substrate preferences beyond the general enoyl-ACP/FAS II role are not established from sequence analysis alone.