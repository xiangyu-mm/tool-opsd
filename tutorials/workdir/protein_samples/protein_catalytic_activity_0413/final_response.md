## Functional identification

The 455-aa protein is most consistent with **GlmU, bifunctional N-acetylglucosamine-1-phosphate uridyltransferase / glucosamine-1-phosphate acetyltransferase**.

This assignment is supported by:

- ~48% amino-acid identity over ~96–98% of the sequence to reviewed bacterial GlmU proteins.
- N-terminal **NTP-transferase/uridyltransferase** domain signatures.
- C-terminal region characteristic of the GlmU acetyltransferase module.
- Curated homologs annotated with EC **2.3.1.157** and EC **2.7.7.23**.

## Catalytic activities

GlmU catalyzes the final two reactions in bacterial UDP-N-acetylglucosamine biosynthesis:

### 1. Glucosamine-1-phosphate acetyltransferase activity

The C-terminal domain transfers an acetyl group from acetyl-CoA to glucosamine-1-phosphate:

\[
\text{α-D-glucosamine-1-phosphate} + \text{acetyl-CoA}
\rightarrow
\text{N-acetyl-α-D-glucosamine-1-phosphate} + \text{CoA} + \mathrm{H^+}
\]

**EC:** 2.3.1.157  
**Rhea:** RHEA:13725

### 2. UDP-N-acetylglucosamine diphosphorylase activity

The N-terminal domain then transfers UMP from UTP to N-acetylglucosamine-1-phosphate:

\[
\text{N-acetyl-α-D-glucosamine-1-phosphate} + \text{UTP} + \mathrm{H^+}
\rightarrow
\text{UDP-N-acetyl-α-D-glucosamine} + \text{PP}_{i}
\]

**EC:** 2.7.7.23  
**Rhea:** RHEA:13509

## Overall pathway reaction

Together, the two activities convert glucosamine-1-phosphate, acetyl-CoA, and UTP into UDP-N-acetylglucosamine:

\[
\text{GlcN-1-P} + \text{acetyl-CoA} + \text{UTP}
\rightarrow
\text{UDP-GlcNAc} + \text{CoA} + \text{PP}_{i}
\]

UDP-GlcNAc is a precursor for **peptidoglycan**, bacterial surface glycans, and—in Gram-negative bacteria—lipid A/lipopolysaccharide biosynthesis.

## Confidence and caveat

The protein is very likely a **bacterial GlmU enzyme**, with **moderate-to-strong homology-based support**. The exact activities are inferred from highly similar reviewed homologs rather than from a direct biochemical assay of this particular sequence. Curated GlmU homologs also indicate binding of one **Mg²⁺ ion per subunit**.