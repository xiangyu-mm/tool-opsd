## Analysis plan

1. [✓] Calculate basic sequence properties and inspect notable motifs.  
2. [✓] Identify close Swiss-Prot homologs and infer the protein family.  
3. [✓] Retrieve functional, catalytic, cofactor, pathway, localization, subunit, and GO annotations.  
4. [✓] Record and review the key evidence in the research graph.  
5. [✓] Present a concise functional summary with evidence limitations.  

## Functional identification

The sequence is **NADH:quinone oxidoreductase subunit C/D**, also called a **NuoC/NuoD fusion protein** of respiratory complex I (NDH-1).

This assignment is exceptionally strong:

- **597 amino acids**
- **100% sequence identity and 100% coverage** to reviewed UniProt entry **Q8K9Y5**
- Exact sequence-hash match to the annotated reference protein
- Pfam evidence for both expected complex-I domains:
  - **Complex1_30kDa / NuoC-like domain:** residues 47–175
  - **Complex1_49kDa / NuoD-like domain:** residues 326–597

## Main biological role

The protein is a component of the **peripheral arm of bacterial respiratory complex I**. Complex I transfers electrons from NADH to quinone and uses the released energy to pump protons across the membrane.

Overall complex-I reaction:

\[
\text{NADH} + \text{quinone} + 5H^+_{\mathrm{in}}
\rightarrow
\text{NAD}^+ + \text{quinol} + 4H^+_{\mathrm{out}}
\]

The queried protein is **not expected to perform this entire reaction independently**. Instead, it forms part of the structural and electron-transfer-associated peripheral sector together with other subunits, including NuoB, NuoE, NuoF, and NuoG.

## Sequence-derived properties

| Feature | Result |
|---|---:|
| Length | 597 aa |
| Estimated molecular mass | 69.34 kDa |
| Theoretical pI | 6.22 |
| Predicted charge at pH 7 | −6.0 |
| GRAVY hydropathy score | −0.255 |
| Aromaticity | 0.116 |
| Instability index | 38.8 |

The moderately negative hydropathy score and the annotation as a **peripheral membrane protein** are consistent with a largely soluble protein associated with the cytoplasmic face of the inner membrane, rather than an integral membrane-spanning subunit.

## Localization and complex organization

- **Localization:** cytoplasmic side of the bacterial inner membrane
- **Membrane association:** peripheral, not a primary transmembrane component
- **Complex:** NDH-1/complex I
- **Complex organization:** bacterial complex I is annotated as a 13-subunit complex in the reference organism
- **Subunit architecture:** the sequence fuses the otherwise separate NuoC- and NuoD-like components into one polypeptide

## Cofactors and catalytic interpretation

The overall complex uses:

- **FMN**
- Multiple **iron–sulfur clusters**
- **Quinone** as the terminal electron acceptor

However, the available evidence does **not** establish that this NuoC/D fusion independently binds FMN or Fe–S centers. Those cofactors are primarily associated with other complex-I peripheral-arm subunits, especially the NuoE/F/G region. Therefore, this protein should be interpreted mainly as a **complex-I structural/peripheral-arm component**, not as a standalone NADH dehydrogenase.

## Associated annotations

Reported GO terms for the matched reference include:

- **NADH dehydrogenase complex**
- **NAD binding**
- **NADH dehydrogenase activity**
- **Ubiquinone binding**
- **Plasma membrane**
- **Respiratory electron transport chain**

These functional terms describe the role of the protein within complex I and should not be taken to mean that the isolated NuoC/D fusion catalyzes complete NADH-to-quinone electron transfer on its own.

## Overall conclusion

**This is a bacterial complex-I NuoC/NuoD fusion protein, approximately 69 kDa, belonging to the peripheral arm of the NADH:quinone oxidoreductase.** It participates in respiratory electron transport and proton-gradient formation through its integration into NDH-1. The identification is supported by an exact reviewed-sequence match and by Pfam domains characteristic of both NuoC and NuoD.