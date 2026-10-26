### Functional identification

The 380-aa protein is most consistent with a **bifunctional IspD/IspF enzyme** in the bacterial methylerythritol phosphate (MEP/DOXP) pathway of isoprenoid biosynthesis.

Evidence:

- **N-terminal IspD domain:** residues approximately 4–215; Pfam IspD, PF01128.
- **C-terminal IspF/YgbB domain:** residues approximately 224–377; Pfam YgbB, PF02542.
- It is highly similar to reviewed bifunctional IspD/IspF proteins, with **61.7–67.5% sequence identity over nearly the entire sequence**.
- Predicted size is approximately **40.3 kDa**.
- The homologous enzyme is annotated as using a **divalent metal cation**, although the exact metal is not established from this sequence alone.

### Catalytic activities

This fusion enzyme carries out two distinct reactions:

1. **IspD activity — MEP cytidylyltransferase**  
   **EC 2.7.7.60; Rhea RHEA:13429**

\[
\text{2-C-methyl-D-erythritol 4-phosphate} + \text{CTP}
\rightarrow
\text{4-CDP-2-C-methyl-D-erythritol} + \text{diphosphate}
\]

This is step 2 of the MEP pathway and activates MEP by forming **CDP-ME**.

2. **IspF activity — ME-cPP synthase**  
   **EC 4.6.1.12; Rhea RHEA:23864**

\[
\text{4-CDP-2-C-methyl-D-erythritol 2-phosphate}
\rightarrow
\text{2-C-methyl-D-erythritol 2,4-cyclic diphosphate} + \text{CMP}
\]

This is step 4 of the MEP pathway and produces **ME-cPP**.

These reactions are not consecutive within the same active site: CDP-ME is first phosphorylated by IspE, a separate enzyme, before the IspF domain converts it to ME-cPP.

### Overall conclusion

**Predicted function:** bifunctional **2-C-methyl-D-erythritol 4-phosphate cytidylyltransferase/2-C-methyl-D-erythritol 2,4-cyclodiphosphate synthase**, commonly designated **IspD/IspF**.

**Biological role:** biosynthesis of isopentenyl diphosphate and downstream terpenoid compounds through the bacterial MEP pathway.

The assignment is strongly supported by domain architecture, near-full-length homology, and matching curated EC/Rhea annotations, but remains a sequence- and homology-based prediction rather than a direct biochemical assay of this particular protein.

Plan:
1. [✓] Analyze sequence properties, domains, motifs, and homologs.
2. [✓] Retrieve catalytic, cofactor, pathway, and reaction annotations.
3. [✓] Record and review the evidence graph.
4. [✓] Integrate the evidence into the final functional and catalytic summary.