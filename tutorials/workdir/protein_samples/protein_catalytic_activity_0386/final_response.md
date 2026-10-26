## Functional annotation

This 471-residue protein is most consistent with **GlmU, a bifunctional UDP-N-acetylglucosamine biosynthesis enzyme**.

The assignment is well supported by:

- 42–53% amino-acid identity to reviewed GlmU proteins
- 96–98% sequence coverage
- Extremely significant homology E-values: approximately \(10^{-116}\) to \(10^{-154}\)
- A matching two-domain architecture:
  - **N-terminal pyrophosphorylase domain**
  - Flexible linker
  - **C-terminal glucosamine-1-phosphate N-acetyltransferase domain**

The predicted protein is approximately **50.1 kDa**, cytosolic, and likely forms a **homotrimer**, as reported for characterized bacterial GlmU proteins.

## Catalytic activities

GlmU catalyzes the final two reactions in the de novo synthesis of UDP-N-acetylglucosamine (UDP-GlcNAc).

### 1. Glucosamine-1-phosphate acetyltransferase

The C-terminal domain transfers an acetyl group from acetyl-CoA to glucosamine-1-phosphate:

\[
\alpha\text{-D-glucosamine-1-phosphate} + \text{acetyl-CoA}
\rightarrow
N\text{-acetyl-}\alpha\text{-D-glucosamine-1-phosphate} + \text{CoA} + \mathrm{H^+}
\]

- EC: **2.3.1.157**
- Rhea: **RHEA:13725**

### 2. UDP-N-acetylglucosamine diphosphorylase

The N-terminal domain then converts N-acetylglucosamine-1-phosphate into UDP-GlcNAc using UTP:

\[
N\text{-acetyl-}\alpha\text{-D-glucosamine-1-phosphate}
+ \text{UTP} + \mathrm{H^+}
\rightarrow
\text{UDP-}N\text{-acetyl-}\alpha\text{-D-glucosamine}
+ \text{diphosphate}
\]

- EC: **2.7.7.23**
- Rhea: **RHEA:13509**

### Overall reaction

Combining the two activities gives:

\[
\alpha\text{-D-glucosamine-1-phosphate}
+ \text{acetyl-CoA}
+ \text{UTP}
\rightarrow
\text{UDP-}N\text{-acetylglucosamine}
+ \text{CoA}
+ \text{diphosphate}
\]

## Biological role

UDP-GlcNAc is a central precursor for:

- **Peptidoglycan biosynthesis**
- Bacterial cell-envelope construction
- **Lipid A/LPS biosynthesis** in Gram-negative bacteria
- Other UDP-sugar-dependent processes

The homolog-based annotations indicate that GlmU binds approximately **one Mg²⁺ ion per subunit**, likely assisting nucleotide-substrate binding and/or pyrophosphate chemistry.

## Confidence and limitations

**High confidence:** the protein is a GlmU-like bifunctional enzyme involved in UDP-GlcNAc biosynthesis.

**Moderate confidence:** the exact oligomeric state, Mg²⁺ stoichiometry, and substrate details are inferred from closely related curated homologs rather than experimentally demonstrated for this specific sequence.