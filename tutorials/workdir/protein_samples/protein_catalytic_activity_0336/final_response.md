1. [✓] Analyze sequence properties, homology, catalytic activity, domains, cofactors, and pathway annotations.  
2. [✓] Store the key protein-function evidence and provenance in the evidence graph.  
3. [✓] Retrieve the stored evidence to verify consistency.  
4. [✓] Provide a concise functional description centered on the chemical reaction.  

## Functional identification

The protein is **asparagine--tRNA ligase** (**AsnRS; EC 6.1.1.22**), a cytoplasmic aminoacyl-tRNA synthetase.

Identification is highly confident because the 450-residue sequence is an **exact sequence match** to reviewed *Enterococcus faecalis* AsnRS UniProt entry **Q831X4**. It also contains the expected:

- **tRNA anticodon-recognition domain**: PF01336  
- **Class II aminoacyl-tRNA synthetase catalytic domain**: PF00152  
- ATP-binding and tRNA-binding functional annotations  
- Homodimeric architecture typical of bacterial AsnRS enzymes  

## Catalyzed reaction

\[
\text{tRNA}^{\mathrm{Asn}} + \text{L-asparagine} + \text{ATP}
\rightarrow
\text{L-asparaginyl-tRNA}^{\mathrm{Asn}} + \text{AMP} + \text{diphosphate} + \mathrm{H^+}
\]

In words, AsnRS attaches **L-asparagine to the 3′-terminal adenosine of tRNA\(^\mathrm{Asn}\)**, producing **asparaginyl-tRNA\(^\mathrm{Asn}\)** for use during protein synthesis.

The reaction proceeds through activation of asparagine as an **asparaginyl-AMP intermediate**, followed by transfer of the activated aminoacyl group to tRNA. ATP is therefore cleaved to **AMP and pyrophosphate**, rather than to ADP.

**Overall role:** charging tRNA\(^\mathrm{Asn}\) with asparagine, thereby supplying correctly aminoacylated tRNA for incorporation of asparagine into newly synthesized proteins.