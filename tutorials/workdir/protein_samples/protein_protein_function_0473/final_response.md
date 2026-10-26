Plan:
1. [✓] Analyze the supplied sequence for basic properties, homologs, domains, function, pathways, and localization.
2. [✓] Record the strongest evidence and inferred annotations in the knowledge graph.
3. [✓] Retrieve the recorded evidence to verify consistency.
4. [✓] Provide a concise functional summary, including confidence and limitations.

## Functional identification

The protein is **glycerol-3-phosphate dehydrogenase [NAD(P)+]**, commonly encoded by **gpsA** in bacteria.

This assignment is very strong: the sequence is **339 amino acids long** and is an exact full-length match to reviewed *Yersinia* proteins annotated as glycerol-3-phosphate dehydrogenase, with:

- **100% sequence identity**
- **100% query and reference coverage**
- E-value approximately **1 × 10⁻²⁴¹**
- Matching N- and C-terminal glycerol-3-phosphate dehydrogenase domains

## Catalytic activity

The enzyme catalyzes the reversible redox reaction:

\[
\text{DHAP} + \text{NAD(P)H} + H^+ \rightleftharpoons \text{sn-glycerol-3-phosphate} + \text{NAD(P)}^+
\]

where DHAP is **dihydroxyacetone phosphate**.

The enzyme is annotated with **EC 1.1.1.94** and can use either **NADH or NADPH**, with corresponding NAD⁺/NADP⁺ reactions represented in Rhea.

## Biological roles

Its main biological role is to produce **sn-glycerol-3-phosphate**, which is a central precursor for:

- **Bacterial glycerophospholipid biosynthesis**
- **Cell membrane formation**
- Glycerol-3-phosphate metabolism
- Broader carbohydrate metabolism

Thus, the protein links glycolytic carbon metabolism to membrane lipid production. In many bacteria, this reaction supplies the glycerol-phosphate backbone required for phosphatidic acid and downstream phospholipid synthesis.

## Cellular location

The protein is expected to be a **soluble cytosolic enzyme**.

Supporting evidence:

- Reviewed homologs are annotated to the **cytoplasm/cytosol**
- The sequence lacks an obvious N-terminal secretion signal
- It has no apparent long hydrophobic transmembrane segments
- Its architecture is consistent with a soluble NAD(P)-dependent metabolic enzyme

## Sequence properties

- Length: **339 residues**
- Predicted molecular mass: **36.2 kDa**
- Theoretical pI: **7.71**
- Predicted domains:
  - **NAD_Gly3P_dh_N**, residues approximately 8–163
  - **NAD_Gly3P_dh_C**, residues approximately 184–323
- A conserved catalytic proton-acceptor feature is annotated near **residue 195**

## Summary

This sequence encodes a **cytosolic, NAD(P)-dependent glycerol-3-phosphate dehydrogenase**. It reversibly interconverts DHAP and glycerol-3-phosphate and likely functions primarily in supplying glycerol-3-phosphate for **bacterial membrane glycerophospholipid synthesis**. The exact sequence match to curated proteins makes this a **high-confidence functional assignment**.