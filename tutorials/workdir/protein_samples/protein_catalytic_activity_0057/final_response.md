## Functional identification

The 398-residue protein is most likely **RibBA**, a bifunctional enzyme in **riboflavin (vitamin B₂) biosynthesis**.

Evidence:

- 57.6–59.4% identity to reviewed RibBA proteins over approximately the full sequence.
- Two matching catalytic domains:
  - **DHBP synthase domain**: residues ~8–197
  - **GTP cyclohydrolase II domain**: residues ~210–372
- Corresponding EC activities:
  - **EC 4.1.99.12** — 3,4-dihydroxy-2-butanone-4-phosphate synthase
  - **EC 3.5.4.25** — GTP cyclohydrolase II

Thus, this protein combines the activities that are sometimes encoded by separate proteins, RibB and RibA, respectively.

## Catalytic reactions

### 1. DHBP synthase activity

The N-terminal domain converts ribulose-5-phosphate into the riboflavin precursor 3,4-dihydroxy-2-butanone 4-phosphate:

\[
\text{D-ribulose-5-phosphate}
\rightarrow
\text{3,4-dihydroxy-2-butanone 4-phosphate}
+
\text{formate}
+
\mathrm{H^+}
\]

The product is also represented in reaction databases as **(2S)-2-hydroxy-3-oxobutyl phosphate**.

This reaction is assigned to **Rhea RHEA:18457**.

### 2. GTP cyclohydrolase II activity

The C-terminal domain initiates the purine-derived branch of riboflavin biosynthesis by converting GTP into a pyrimidine intermediate:

\[
\text{GTP} + 4\mathrm{H_2O}
\rightarrow
\text{2,5-diamino-6-hydroxy-4-(5-phosphoribosylamino)pyrimidine}
+
\text{formate}
+
2\mathrm{P_i}
+
3\mathrm{H^+}
\]

The product is commonly called **DARP**:  
**2,5-diamino-6-ribosylamino-4(3H)-pyrimidinone 5′-phosphate**. Some database representations describe the phosphate products as pyrophosphate, reflecting reaction-balancing or protonation conventions.

This reaction is assigned to **Rhea RHEA:23704**.

## Cofactors and active-site chemistry

Homologous RibBA proteins are annotated as binding:

- **Two divalent metal ions**, typically Mg²⁺ or Mn²⁺
- **One Zn²⁺ ion**

The metals are expected to support phosphate/substrate binding and catalysis. The homologous GTP cyclohydrolase II active-site residues include a proton-accepting residue and a nucleophilic residue near the equivalent of positions ~328–330.

## Overall conclusion

This sequence encodes a **cytosolic bifunctional RibBA enzyme** that catalyzes two early, complementary reactions in riboflavin biosynthesis:

1. Formation of **3,4-dihydroxy-2-butanone 4-phosphate** from ribulose-5-phosphate.
2. Conversion of **GTP to DARP**, a precursor of the pyrimidine portion of riboflavin.

The assignment is strongly supported by full-length homology and domain architecture, although it remains a sequence-based inference rather than direct biochemical characterization of this exact protein.