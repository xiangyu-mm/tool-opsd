Plan completion:

1. [✓] Analyze sequence properties, motifs, and domain architecture.
2. [✓] Compare with annotated homologs and retrieve functional evidence.
3. [✓] Record and review the key findings with provenance.
4. [✓] Present the functional summary and evidence limitations.

## Functional summary

The 342-amino-acid protein is very likely a **pyrophosphate-dependent phosphofructokinase (PPi-PFK)**, also called **diphosphate–fructose-6-phosphate 1-phosphotransferase**.

It most closely matches the reviewed *Streptomyces coelicolor* enzyme O08333:

- **86.8% sequence identity**
- **100% query and target coverage**
- **E-value: 1 × 10⁻²²²**

This level of full-length similarity provides strong support for the functional assignment.

### Proposed reaction

\[
\text{D-fructose-6-phosphate} + \text{PPi}
\rightleftharpoons
\text{D-fructose-1,6-bisphosphate} + \text{Pi}
\]

- **EC number:** EC 2.7.1.90  
- **Rhea reaction:** RHEA:13613  
- **Cofactor:** Mg²⁺  
- **Pathway:** Glycolysis and potentially gluconeogenesis  

Unlike conventional ATP-dependent phosphofructokinase, PPi-PFK uses **inorganic pyrophosphate (PPi)** as the phosphoryl donor. Because the reaction is reversible, the enzyme can support both glycolytic and gluconeogenic metabolism.

## Sequence and structural features

| Feature | Result |
|---|---:|
| Length | 342 aa |
| Estimated molecular mass | 36.4 kDa |
| Theoretical pI | 6.07 |
| Predicted charge at pH 7 | −4.6 |
| Instability index | 23.1 |
| Pfam domain | PFK, PF00365.26 |
| Pfam span | Residues 2–298 |

The sequence contains a nearly full-length **PFK catalytic domain**, consistent with a compact soluble metabolic enzyme. The sequence-derived instability index is below the commonly used instability threshold, although this is only a computational estimate.

## Catalytic and cellular properties

Based on the close reviewed homologs, the protein is expected to be:

- **Cytoplasmic**
- **Mg²⁺-dependent**
- A **homodimer or homotetramer**
- Generally **non-allosteric**
- Involved in the first committed phosphorylation step of glycolysis

Conserved homolog features include catalytic and substrate-binding residues in the approximate regions corresponding to residues **104, 125–128, 163–172, 222, and 266–275** in the reference proteins. Exact residue mapping to this sequence was not independently performed, so these positions should be treated as reference-site locations rather than definitive assignments in the query protein.

## Relevant functional annotations

Supported annotations include:

- **6-phosphofructokinase activity**
- **Diphosphate-fructose-6-phosphate 1-phosphotransferase activity**
- **Fructose-6-phosphate binding**
- **Fructose-1,6-bisphosphate metabolism**
- **Canonical glycolysis**
- **6-phosphofructokinase complex**

## Confidence and caveats

**Overall confidence: high.** The assignment is supported by a reviewed, full-length homolog with very high sequence identity and by a matching Pfam PFK domain.

The retrieved database also lists ATP-dependent phosphofructokinase reactions among broader homolog annotations. However, those reactions should not be assigned to this sequence solely from the search output. The strongest specific evidence supports **PPi-dependent phosphofructokinase activity**. Experimental enzyme assays would be required to confirm donor specificity, kinetic parameters, oligomeric state, and regulation for this particular protein.