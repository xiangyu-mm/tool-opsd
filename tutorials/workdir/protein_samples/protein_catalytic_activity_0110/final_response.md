## Functional assignment

The 197-residue protein is most consistent with a **Ham1p-like dITP/XTP pyrophosphatase**, also called a **noncanonical purine nucleoside-triphosphate pyrophosphatase**.

Evidence:

- Pfam **Ham1p_like (PF01725)** domain spanning nearly the entire sequence.
- Strong similarity to reviewed dITP/XTP pyrophosphatases:
  - ~49–52% sequence identity
  - ~90–97% alignment coverage
  - E-values around \(10^{-53}\)–\(10^{-54}\)
- Closest characterized homologs have **EC 3.6.1.66** activity and bind **Mg²⁺**.

## Catalytic activity

The enzyme hydrolyzes the phosphoanhydride bond of abnormal purine nucleoside triphosphates:

\[
\text{XTP} + H_2O \rightarrow \text{XMP} + PP_i + H^+
\]

\[
\text{dITP} + H_2O \rightarrow \text{dIMP} + PP_i + H^+
\]

\[
\text{ITP} + H_2O \rightarrow \text{IMP} + PP_i + H^+
\]

where:

- **XTP** = xanthosine triphosphate  
- **dITP** = deoxyinosine triphosphate  
- **ITP** = inosine triphosphate  
- \(PP_i\) = inorganic diphosphate/pyrophosphate  

The preferred substrates are generally **XTP, dITP, and ITP**, rather than canonical ATP or GTP.

## Biological role

This is likely a **nucleotide-pool “house-cleaning” enzyme**. By removing noncanonical purine triphosphates, it helps prevent their incorporation into DNA or RNA, thereby reducing potential replication and transcription errors.

The reaction is expected to be **Mg²⁺-dependent**, based on the characterized homologs.

## Confidence and caveats

**Confidence: moderate to high for the enzyme family and general reaction.** The near-complete, high-identity matches and full-length Ham1p-like domain strongly support this assignment. However, the sequence contains several ambiguous `X` residues, and exact substrate preference cannot be experimentally confirmed from sequence alone. The most defensible annotation is:

> **Mg²⁺-dependent Ham1p-like dITP/XTP pyrophosphatase that hydrolyzes noncanonical purine nucleoside triphosphates to their monophosphates and inorganic diphosphate.**