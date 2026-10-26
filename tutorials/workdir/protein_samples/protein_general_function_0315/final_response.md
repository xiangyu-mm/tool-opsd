## Functional summary

The 531-residue protein is very likely a **bacterial CTP synthase (CTPS; EC 6.3.4.2)**, an enzyme in de novo pyrimidine biosynthesis.

### Key evidence

- **Strong homology to curated CTP synthases**
  - 59.5–61.1% amino-acid identity
  - ~99.6–99.8% query coverage
  - E-values approximately \(10^{-232}\) to \(10^{-238}\)
- **Characteristic two-domain architecture**
  - **N-terminal CTP synthetase/ amidoligase domain:** residues ~2–266
  - **C-terminal class-I glutamine amidotransferase domain:** residues ~301–524
- The protein length and domain arrangement closely match known bacterial CTPS proteins.

### Predicted reaction

The primary reaction is:

\[
\text{UTP} + \text{L-glutamine} + \text{ATP} + \text{H}_2\text{O}
\rightarrow
\text{CTP} + \text{L-glutamate} + \text{ADP} + \text{phosphate}
\]

The enzyme may also use free ammonia as an alternative nitrogen source:

\[
\text{UTP} + \text{NH}_4^+ + \text{ATP}
\rightarrow
\text{CTP} + \text{ADP} + \text{phosphate}
\]

The C-terminal glutaminase domain hydrolyzes glutamine to generate ammonia, while the N-terminal synthetase domain uses ATP to aminate UTP.

### Sequence-derived features

| Feature | Estimate |
|---|---:|
| Length | 531 aa |
| Molecular mass | 59.1 kDa |
| Theoretical pI | 5.49 |
| Net charge at pH 7 | −16.0 |
| GRAVY | −0.21 |
| Instability index | 36.9 |

The sequence is acidic overall and lacks an obvious long hydrophobic region or signal peptide, consistent with a **soluble cytosolic enzyme**.

### Biological role

The protein likely functions in:

- **De novo CTP biosynthesis**
- Pyrimidine nucleotide metabolism
- Regulation of intracellular CTP pools

Curated homologs are annotated as **homotetramers**. They are reported to be allosterically:

- Activated by **GTP** when glutamine is the nitrogen source
- Inhibited by product **CTP**

These regulatory properties are plausible for this sequence but remain **homology-based predictions**, not direct experimental observations for the supplied protein.

### Confidence and caveats

**Overall identification confidence: high.** The near-full-length sequence matches reviewed CTP synthases, and the domain organization is diagnostic.

The additional Peptidase_C26 match lies within the glutaminase region and should not be interpreted as evidence that this protein is a protease. Exact substrate preference, oligomeric state, and allosteric regulation would require direct biochemical or structural validation.